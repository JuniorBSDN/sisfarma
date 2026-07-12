import os
from fastapi import FastAPI, HTTPException, status, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field
from typing import Optional
import bcrypt
import jwt

app = FastAPI(
    title="YANA API - Central de Abastecimento Farmacêutico (PostgreSQL)",
    description="Backend em nuvem para controle interno e rastreabilidade hospitalar (multi-empresa)",
    version="1.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

# ⚠️ Configure esta variável no Vercel (Settings > Environment Variables).
# Se não configurar, os tokens ficam previsíveis e inseguros.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "troque-esta-chave-no-vercel")
JWT_ALGORITHM = "HS256"
JWT_EXPIRA_HORAS = 12


# 🛠️ GERENCIADOR DE CONEXÃO E ESTRUTURA DO BANCO DE DADOS
def conectar_bd():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # 1. TABELA DE USUÁRIOS (cada usuário aqui É uma empresa/unidade cliente)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                usuario VARCHAR(150) UNIQUE NOT NULL,
                senha VARCHAR(255) NOT NULL,
                perfil VARCHAR(150) NOT NULL
            );
        """)

        # 2. TABELA DE MEDICAMENTOS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS medicamentos (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                principio_ativo VARCHAR(255) NOT NULL,
                categoria VARCHAR(150) NOT NULL,
                controlado INT NOT NULL,
                codigo_barras VARCHAR(150),
                empresa_id INT REFERENCES usuarios(id) ON DELETE CASCADE
            );
        """)
        cursor.execute("ALTER TABLE medicamentos ADD COLUMN IF NOT EXISTS empresa_id INT REFERENCES usuarios(id) ON DELETE CASCADE;")

        # Código de barras deve ser único POR EMPRESA, não globalmente
        cursor.execute("DROP INDEX IF EXISTS medicamentos_codigo_barras_key;")
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_medicamentos_ean_empresa
            ON medicamentos (empresa_id, codigo_barras)
            WHERE codigo_barras IS NOT NULL AND codigo_barras <> 'Nenhum';
        """)

        # 3. TABELA DE LOTES DE MEDICAMENTOS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lotes (
                id SERIAL PRIMARY KEY,
                medicamento_id INT REFERENCES medicamentos(id) ON DELETE CASCADE,
                numero_lote VARCHAR(150) NOT NULL,
                fabricante VARCHAR(255) NOT NULL,
                data_fabricacao DATE,
                validade DATE NOT NULL,
                quantidade INT NOT NULL
            );
        """)

        # 4. TABELA DE INSUMOS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insumos (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                especificacao TEXT,
                unidade_medida VARCHAR(50) NOT NULL,
                grupo VARCHAR(150) NOT NULL,
                empresa_id INT REFERENCES usuarios(id) ON DELETE CASCADE
            );
        """)
        cursor.execute("ALTER TABLE insumos ADD COLUMN IF NOT EXISTS empresa_id INT REFERENCES usuarios(id) ON DELETE CASCADE;")

        # 5. TABELA DE LOTES DE INSUMOS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lotes_insumos (
                id SERIAL PRIMARY KEY,
                insumo_id INT REFERENCES insumos(id) ON DELETE CASCADE,
                numero_lote VARCHAR(150) NOT NULL,
                fabricante VARCHAR(255) NOT NULL,
                validade DATE NOT NULL,
                quantidade INT NOT NULL
            );
        """)

        # 6. TABELA DE MOVIMENTAÇÕES / AUDITORIA
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS movimentacoes (
                id SERIAL PRIMARY KEY,
                lote_id INT,
                insumo_lote_id INT,
                tipo VARCHAR(100) NOT NULL,
                quantidade INT NOT NULL,
                setor_destino VARCHAR(150),
                paciente_nome VARCHAR(255),
                prescricao_num VARCHAR(150),
                responsavel VARCHAR(255),
                data_movimentacao VARCHAR(50) NOT NULL,
                empresa_id INT REFERENCES usuarios(id) ON DELETE CASCADE
            );
        """)
        cursor.execute("ALTER TABLE movimentacoes ADD COLUMN IF NOT EXISTS empresa_id INT REFERENCES usuarios(id) ON DELETE CASCADE;")

        # 7. TABELA DE TECNOVIGILÂNCIA
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tecnovigilancia (
                id SERIAL PRIMARY KEY,
                lote_texto VARCHAR(255) NOT NULL,
                tipo_ocorrencia VARCHAR(150) NOT NULL,
                descricao TEXT NOT NULL,
                gravidade VARCHAR(100) NOT NULL,
                conduta TEXT NOT NULL,
                data_registro VARCHAR(50) NOT NULL,
                operador VARCHAR(255) NOT NULL,
                empresa_id INT REFERENCES usuarios(id) ON DELETE CASCADE
            );
        """)
        cursor.execute("ALTER TABLE tecnovigilancia ADD COLUMN IF NOT EXISTS empresa_id INT REFERENCES usuarios(id) ON DELETE CASCADE;")

        conn.commit()
        cursor.close()
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao conectar ou estruturar o PostgreSQL na nuvem: {str(e)}")


# =========================================================================
# 🔐 AUTENTICAÇÃO / SESSÃO (JWT por empresa)
# =========================================================================
def obter_empresa_atual(authorization: Optional[str] = Header(None)):
    """Extrai e valida o token Bearer, retornando qual empresa está logada.
    Toda rota operacional (medicamentos, lotes, dispensação, etc.) depende disso."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sessão ausente. Faça login novamente.")

    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Sessão inválida. Faça login novamente.")

    return {"empresa_id": payload["empresa_id"], "usuario": payload["usuario"], "perfil": payload["perfil"]}


# =========================================================================
# MODELOS DE DADOS (VALIDAÇÃO PYDANTIC)
# =========================================================================
class LoginSchema(BaseModel):
    usuario: str
    senha: str


class MedicamentoSchema(BaseModel):
    nome: str = Field(..., min_length=1)
    principio_ativo: str = Field(..., min_length=1)
    categoria: str
    controlado: int
    codigo_barras: str


class LoteMedicamentoSchema(BaseModel):
    medicamento_id: int
    numero_lote: str
    fabricante: str
    data_fabricacao: Optional[str] = None
    validade: str
    quantidade: int = Field(..., gt=0)


class InsumoSchema(BaseModel):
    nome: str = Field(..., min_length=1)
    especificacao: str
    unidade_medida: str
    grupo: str


class LoteInsumoSchema(BaseModel):
    insumo_id: int
    numero_lote: str
    fabricante: str
    data_fabricacao: Optional[str] = None
    validade: str
    quantidade: int = Field(..., gt=0)


class DispensacaoSchema(BaseModel):
    tipo_material: str
    lote_id: int
    quantidade: int = Field(..., gt=0)
    setor_destino: str
    paciente_nome: str
    prescricao_num: str
    responsavel: str


class TecnovigilanciaSchema(BaseModel):
    lote_suspeito: str
    tipo_ocorrencia: str
    descricao: str
    gravidade: str
    conduta_imediata: str
    operador: str


class VerificarAdminSchema(BaseModel):
    senha: str


class AktualizarUsuarioSchema(BaseModel):
    usuario: str
    senha: Optional[str] = None  # Vazio/ausente = mantém a senha atual
    perfil: str


class RegistrarUsuarioSchema(BaseModel):
    usuario: str
    senha: str
    perfil: str


# =====================================================================
# 📊 DASHBOARD (escopado por empresa)
# =====================================================================
@app.get("/api/dashboard/resumo", tags=["Auditoria Sanitária"])
def obter_resumo_dashboard_vencidos(empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()
    data_atual = date.today()

    cursor.execute("""
        SELECT med.nome, l.numero_lote, l.validade, l.quantidade
        FROM lotes l
        JOIN medicamentos med ON l.medicamento_id = med.id
        WHERE l.quantidade > 0 AND l.validade <= %s AND med.empresa_id = %s
    """, (data_atual, empresa["empresa_id"]))
    lotes_med = cursor.fetchall()

    cursor.execute("""
        SELECT i.nome, li.numero_lote, li.validade, li.quantidade
        FROM lotes_insumos li
        JOIN insumos i ON li.insumo_id = i.id
        WHERE li.quantidade > 0 AND li.validade <= %s AND i.empresa_id = %s
    """, (data_atual, empresa["empresa_id"]))
    lotes_ins = cursor.fetchall()
    db.close()

    alertas = []
    for r in lotes_med:
        alertas.append({"tipo": "MEDICAMENTO VENCIDO", "detalhe": f"{r['nome']} (Lote: {r['numero_lote']})",
                        "validade": str(r['validade']), "estoque": r['quantidade']})
    for r in lotes_ins:
        alertas.append({"tipo": "INSUMO VENCIDO", "detalhe": f"{r['nome']} (Lote: {r['numero_lote']})",
                        "validade": str(r['validade']), "estoque": r['quantidade']})

    return {"vencidos": alertas, "total_criticos": len(alertas)}


# =====================================================================
# GERENCIAMENTO DE ACESSOS E UNIDADES (PAINEL ADMIN MASTER)
# Continua global de propósito: o admin master gerencia TODAS as empresas.
# =====================================================================
@app.delete("/api/auth/usuarios/{usuario_id}", tags=["Autenticação"])
def deletar_usuario_unidade(usuario_id: int):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Unidade/Acesso revogado com sucesso."}


@app.put("/api/auth/usuarios/{usuario_id}", tags=["Autenticação"])
def atualizar_usuario_unidade(usuario_id: int, dados: AktualizarUsuarioSchema):
    db = conectar_bd()
    cursor = db.cursor()

    if dados.senha:
        senha_hash = bcrypt.hashpw(dados.senha.encode(), bcrypt.gensalt()).decode()
        cursor.execute(
            "UPDATE usuarios SET usuario = %s, senha = %s, perfil = %s WHERE id = %s",
            (dados.usuario, senha_hash, dados.perfil, usuario_id)
        )
    else:
        cursor.execute(
            "UPDATE usuarios SET usuario = %s, perfil = %s WHERE id = %s",
            (dados.usuario, dados.perfil, usuario_id)
        )

    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Dados da unidade atualizados."}


@app.post("/api/auth/verificar-admin", tags=["Autenticação"])
def verificar_senha_master_admin(dados: VerificarAdminSchema):
    senha_env = os.getenv("admin_password") or os.getenv("ADMIN_PASSWORD") or os.getenv("ADMIN_MASTER_PASSWORD")
    if not senha_env:
        raise HTTPException(status_code=500, detail="Senha master não configurada no servidor (defina ADMIN_PASSWORD nas variáveis de ambiente).")

    if dados.senha.strip() == senha_env.strip():
        return {"status": "sucesso", "autorizado": True}

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Senha Master de Administrador incorreta.")


@app.post("/api/auth/registrar", tags=["Autenticação"])
def registrar_novo_usuario_unidade(dados: RegistrarUsuarioSchema):
    db = conectar_bd()
    cursor = db.cursor()
    senha_hash = bcrypt.hashpw(dados.senha.encode(), bcrypt.gensalt()).decode()
    try:
        cursor.execute(
            "INSERT INTO usuarios (usuario, senha, perfil) VALUES (%s, %s, %s)",
            (dados.usuario, senha_hash, dados.perfil)
        )
        db.commit()
    except psycopg2.errors.UniqueViolation:
        db.close()
        raise HTTPException(status_code=400, detail="Este nome de usuário já está associado a uma unidade ativa.")
    db.close()
    return {"status": "sucesso", "mensagem": "Unidade e credenciais ativadas na nuvem."}


@app.get("/api/auth/usuarios", tags=["Autenticação"])
def listar_usuarios_unidades():
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id, usuario, perfil FROM usuarios ORDER BY id DESC")
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/auth/login", tags=["Autenticação"])
def login(dados: LoginSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id, usuario, senha, perfil FROM usuarios WHERE usuario=%s", (dados.usuario,))
    user = cursor.fetchone()
    db.close()

    senha_valida = user and bcrypt.checkpw(dados.senha.encode(), user["senha"].encode())
    if not senha_valida:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas.")

    token = jwt.encode({
        "empresa_id": user["id"],
        "usuario": user["usuario"],
        "perfil": user["perfil"],
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRA_HORAS)
    }, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    return {"status": "sucesso", "token": token, "usuario": user["usuario"], "perfil": user["perfil"]}


# =========================================================================
# ENDPOINTS OPERACIONAIS (MEDICAMENTOS, INSUMOS E LOTES) — todos escopados por empresa
# =========================================================================
@app.get("/api/medicamentos", tags=["Medicamentos"])
def listar_medicamentos(empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute(
        "SELECT id, nome, principio_ativo, categoria, codigo_barras, controlado FROM medicamentos WHERE empresa_id = %s",
        (empresa["empresa_id"],)
    )
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/medicamentos", tags=["Medicamentos"])
def cadastrar_medicamento(med: MedicamentoSchema, empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO medicamentos (nome, principio_ativo, categoria, controlado, codigo_barras, empresa_id) VALUES (%s,%s,%s,%s,%s,%s)",
            (med.nome, med.principio_ativo, med.categoria, med.controlado, med.codigo_barras, empresa["empresa_id"])
        )
        db.commit()
    except psycopg2.errors.UniqueViolation:
        db.close()
        raise HTTPException(status_code=400, detail="Este Código de Barras já existe no seu catálogo.")
    db.close()
    return {"status": "sucesso", "mensagem": f"Medicamento '{med.nome}' catalogado."}


@app.put("/api/medicamentos/{med_id}", tags=["Medicamentos"])
def atualizar_medicamento(med_id: int, med: MedicamentoSchema, empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE medicamentos
            SET nome = %s, principio_ativo = %s, categoria = %s, controlado = %s, codigo_barras = %s
            WHERE id = %s AND empresa_id = %s
        """, (med.nome, med.principio_ativo, med.categoria, med.controlado, med.codigo_barras, med_id, empresa["empresa_id"]))
        db.commit()
    except psycopg2.errors.UniqueViolation:
        db.close()
        raise HTTPException(status_code=400, detail="Este Código de Barras já está associado a outro medicamento seu.")
    db.close()
    return {"status": "sucesso", "mensagem": f"Cadastro do medicamento '{med.nome}' atualizado com sucesso."}


@app.get("/api/lotes/medicamentos", tags=["Lotes & Estoque"])
def listar_lotes_medicamentos(empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT l.id, med.nome as medicamento, l.numero_lote, l.fabricante, l.validade, l.quantidade
        FROM lotes l JOIN medicamentos med ON l.medicamento_id = med.id
        WHERE l.quantidade > 0 AND med.empresa_id = %s
    """, (empresa["empresa_id"],))
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/lotes/medicamentos", tags=["Lotes & Estoque"])
def receber_lote_medicamento(lote: LoteMedicamentoSchema, empresa=Depends(obter_empresa_atual)):
    try:
        data_validade = datetime.strptime(lote.validade, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data de validade inválido. Use AAAA-MM-DD.")

    db = conectar_bd()
    cursor = db.cursor()

    # Garante que o medicamento pertence à empresa logada
    cursor.execute("SELECT id FROM medicamentos WHERE id = %s AND empresa_id = %s", (lote.medicamento_id, empresa["empresa_id"]))
    if not cursor.fetchone():
        db.close()
        raise HTTPException(status_code=404, detail="Medicamento não encontrado no seu catálogo.")

    fabricacao = lote.data_fabricacao if lote.data_fabricacao else None
    cursor.execute(
        "INSERT INTO lotes (medicamento_id, numero_lote, fabricante, data_fabricacao, validade, quantidade) VALUES (%s,%s,%s,%s,%s,%s)",
        (lote.medicamento_id, lote.numero_lote, lote.fabricante, fabricacao, data_validade, lote.quantidade)
    )
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Lote de medicamento incorporado."}


@app.get("/api/insumos", tags=["Insumos"])
def listar_insumos(empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute(
        "SELECT id, nome, especificacao, unidade_medida, grupo FROM insumos WHERE empresa_id = %s",
        (empresa["empresa_id"],)
    )
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/insumos", tags=["Insumos"])
def cadastrar_insumo(ins: InsumoSchema, empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO insumos (nome, especificacao, unidade_medida, grupo, empresa_id) VALUES (%s, %s, %s, %s, %s)",
        (ins.nome, ins.especificacao, ins.unidade_medida, ins.grupo, empresa["empresa_id"])
    )
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": f"Insumo '{ins.nome}' catalogado."}


@app.get("/api/lotes/insumos", tags=["Lotes & Estoque"])
def listar_lotes_insumos(empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT li.id, i.nome as insumo, li.numero_lote, li.fabricante, li.validade, li.quantidade
        FROM lotes_insumos li JOIN insumos i ON li.insumo_id = i.id
        WHERE li.quantidade > 0 AND i.empresa_id = %s
    """, (empresa["empresa_id"],))
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/lotes/insumos", tags=["Lotes & Estoque"])
def receber_lote_insumo(lote: LoteInsumoSchema, empresa=Depends(obter_empresa_atual)):
    try:
        data_validade = datetime.strptime(lote.validade, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data de validade inválido. Use AAAA-MM-DD.")

    db = conectar_bd()
    cursor = db.cursor()

    # Garante que o insumo pertence à empresa logada
    cursor.execute("SELECT id FROM insumos WHERE id = %s AND empresa_id = %s", (lote.insumo_id, empresa["empresa_id"]))
    if not cursor.fetchone():
        db.close()
        raise HTTPException(status_code=404, detail="Insumo não encontrado no seu catálogo.")

    # 🐛 CORRIGIDO: a coluna correta é 'quantidade' (antes estava 'quantity', causando erro 500)
    cursor.execute(
        "INSERT INTO lotes_insumos (insumo_id, numero_lote, fabricante, validade, quantidade) VALUES (%s, %s, %s, %s, %s)",
        (lote.insumo_id, lote.numero_lote, lote.fabricante, data_validade, lote.quantidade)
    )
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Lote de insumo incorporado ao inventário."}


# =====================================================================
# ⚡ DISPENSAÇÃO UNIFICADA E RASTREABILIDADE SANITÁRIA
# =====================================================================
@app.post("/api/dispensacao", tags=["Dispensação unificada"])
def processar_dispensacao(disp: DispensacaoSchema, empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()

    try:
        if disp.tipo_material == "MEDICAMENTO":
            # Trava de linha + valida que o lote pertence à empresa logada
            cursor.execute("""
                SELECT l.quantidade FROM lotes l
                JOIN medicamentos m ON l.medicamento_id = m.id
                WHERE l.id = %s AND m.empresa_id = %s FOR UPDATE
            """, (disp.lote_id, empresa["empresa_id"]))
            lote = cursor.fetchone()
            if not lote:
                raise HTTPException(status_code=404, detail="Lote não encontrado no seu estoque.")
            if lote["quantidade"] < disp.quantidade:
                raise HTTPException(status_code=400, detail="Saldo insuficiente no lote de medicamento.")

            cursor.execute("UPDATE lotes SET quantidade = quantidade - %s WHERE id = %s",
                           (disp.quantidade, disp.lote_id))

            cursor.execute("""
                INSERT INTO movimentacoes (lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao, empresa_id)
                VALUES (%s, NULL, 'SAÍDA MEDICAMENTO', %s, %s, %s, %s, %s, %s, %s)
            """, (disp.lote_id, disp.quantidade, disp.setor_destino, disp.paciente_nome, disp.prescricao_num,
                  disp.responsavel, datetime.now().strftime("%Y-%m-%d %H:%M"), empresa["empresa_id"]))

        elif disp.tipo_material == "INSUMO":
            cursor.execute("""
                SELECT li.quantidade FROM lotes_insumos li
                JOIN insumos i ON li.insumo_id = i.id
                WHERE li.id = %s AND i.empresa_id = %s FOR UPDATE
            """, (disp.lote_id, empresa["empresa_id"]))
            lote = cursor.fetchone()
            if not lote:
                raise HTTPException(status_code=404, detail="Lote de insumo não encontrado no seu estoque.")
            if lote["quantidade"] < disp.quantidade:
                raise HTTPException(status_code=400, detail="Saldo insuficiente no lote de insumo.")

            cursor.execute("UPDATE lotes_insumos SET quantidade = quantidade - %s WHERE id = %s",
                           (disp.quantidade, disp.lote_id))

            cursor.execute("""
                INSERT INTO movimentacoes (lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao, empresa_id)
                VALUES (NULL, %s, 'SAÍDA INSUMO', %s, %s, %s, %s, %s, %s, %s)
            """, (disp.lote_id, disp.quantidade, disp.setor_destino, disp.paciente_nome, disp.prescricao_num,
                  disp.responsavel, datetime.now().strftime("%Y-%m-%d %H:%M"), empresa["empresa_id"]))
        else:
            raise HTTPException(status_code=400, detail="Tipo de material inválido.")

        db.commit()
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Erro interno na transação: {str(e)}")
    finally:
        db.close()

    return {"status": "sucesso", "mensagem": "Dispensação processada com sucesso!"}


@app.get("/api/auditoria/movimentacoes", tags=["Auditoria & Compliance"])
def relatorio_rastreabilidade(empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao
        FROM movimentacoes
        WHERE empresa_id = %s
        ORDER BY id DESC
    """, (empresa["empresa_id"],))
    rows = cursor.fetchall()
    db.close()
    return rows


@app.get("/api/auditoria/alertas", tags=["Auditoria & Compliance"])
def verificar_alertas_sanitarios(empresa=Depends(obter_empresa_atual)):
    data_atual = datetime.now().date()
    db = conectar_bd()
    cursor = db.cursor()

    cursor.execute("""
        SELECT m.nome, l.numero_lote, l.validade, l.quantidade
        FROM lotes l
        JOIN medicamentos m ON l.medicamento_id = m.id
        WHERE l.quantidade > 0 AND l.validade <= %s AND m.empresa_id = %s
    """, (data_atual, empresa["empresa_id"]))
    lotes_med = cursor.fetchall()

    # 🐛 CORRIGIDO: era 'l.quantidade' (alias inexistente); o correto é 'li.quantidade'
    cursor.execute("""
        SELECT i.nome, li.numero_lote, li.validade, li.quantidade
        FROM lotes_insumos li
        JOIN insumos i ON li.insumo_id = i.id
        WHERE li.quantidade > 0 AND li.validade <= %s AND i.empresa_id = %s
    """, (data_atual, empresa["empresa_id"]))
    lotes_ins = cursor.fetchall()
    db.close()

    alertas = []
    for r in lotes_med:
        alertas.append({"tipo": "MEDICAMENTO VENCIDO", "detalhe": f"{r['nome']} (Lote: {r['numero_lote']})",
                        "validade": str(r['validade']), "estoque": r['quantidade']})
    for r in lotes_ins:
        alertas.append({"tipo": "INSUMO VENCIDO", "detalhe": f"{r['nome']} (Lote: {r['numero_lote']})",
                        "validade": str(r['validade']), "estoque": r['quantidade']})

    return {"vencidos": alertas, "total_criticos": len(alertas)}


@app.post("/api/tecnovigilancia", tags=["Tecnovigilância (POP.FARM.019)"])
def registrar_ocorrencia(event: TecnovigilanciaSchema, empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO tecnovigilancia (lote_texto, tipo_ocorrencia, descricao, gravidade, conduta, data_registro, operador, empresa_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        event.lote_suspeito,
        event.tipo_ocorrencia,
        event.descricao,
        event.gravidade,
        event.conduta_imediata,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        event.operador,
        empresa["empresa_id"]
    ))
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Ocorrência sanitária protocolada."}


@app.get("/api/tecnovigilancia", tags=["Tecnovigilância (POP.FARM.019)"])
def listar_ocorrencias_tecnovigilancia(empresa=Depends(obter_empresa_atual)):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, lote_texto AS lote_suspeito, tipo_ocorrencia, gravidade, data_registro, operador
        FROM tecnovigilancia
        WHERE empresa_id = %s
        ORDER BY id DESC
    """, (empresa["empresa_id"],))
    rows = cursor.fetchall()
    db.close()
    return rows


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
