import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date

import psycopg2
from psycopg2.extras import RealDictCursor  # Mantém o acesso às colunas por nome
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

app = FastAPI(
    title="YANA API - Central de Abastecimento Farmacêutico (PostgreSQL)",
    description="Backend em nuvem para controle interno e rastreabilidade hospitalar",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")


# 🛠️ GERENCIADOR DE CONEXÃO E ESTRUTURA DO BANCO DE DADOS
def conectar_bd():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # 1. TABELA DE USUÁRIOS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                usuario VARCHAR(150) UNIQUE NOT NULL,
                senha VARCHAR(255) NOT NULL,
                perfil VARCHAR(150) NOT NULL
            );
        """)

        # 2. TABELA DE MEDICAMENTOS (Isolada por usuario_dono)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS medicamentos (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                principio_ativo VARCHAR(255) NOT NULL,
                categoria VARCHAR(150) NOT NULL,
                controlado INT NOT NULL,
                codigo_barras VARCHAR(150),
                usuario_dono VARCHAR(150) NOT NULL DEFAULT 'admin'
            );
        """)

        # 3. TABELA DE LOTES DE MEDICAMENTOS (Isolada por usuario_dono)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lotes (
                id SERIAL PRIMARY KEY,
                medicamento_id INT REFERENCES medicamentos(id) ON DELETE CASCADE,
                numero_lote VARCHAR(150) NOT NULL,
                fabricante VARCHAR(255) NOT NULL,
                data_fabricacao DATE,
                validade DATE NOT NULL,
                quantidade INT NOT NULL,
                usuario_dono VARCHAR(150) NOT NULL DEFAULT 'admin'
            );
        """)

        # 4. TABELA DE INSUMOS (Isolada por usuario_dono)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insumos (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                especificacao TEXT,
                unidade_medida VARCHAR(50) NOT NULL,
                grupo VARCHAR(150) NOT NULL,
                usuario_dono VARCHAR(150) NOT NULL DEFAULT 'admin'
            );
        """)

        # 5. TABELA DE LOTES DE INSUMOS (Isolada por usuario_dono)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lotes_insumos (
                id SERIAL PRIMARY KEY,
                insumo_id INT REFERENCES insumos(id) ON DELETE CASCADE,
                numero_lote VARCHAR(150) NOT NULL,
                fabricante VARCHAR(255) NOT NULL,
                validade DATE NOT NULL,
                quantidade INT NOT NULL,
                usuario_dono VARCHAR(150) NOT NULL DEFAULT 'admin'
            );
        """)

        # 6. TABELA DE MOVIMENTAÇÕES / AUDITORIA (Isolada por usuario_dono)
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
                usuario_dono VARCHAR(150) NOT NULL DEFAULT 'admin'
            );
        """)

        # 7. TABELA DE TECNOVIGILÂNCIA (Isolada por usuario_dono)
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
                usuario_dono VARCHAR(150) NOT NULL DEFAULT 'admin'
            );
        """)

        conn.commit()
        cursor.close()
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao conectar ou estruturar o PostgreSQL: {str(e)}")


# =========================================================================
# MODELOS DE DADOS (VALIDAÇÃO PYDANTIC COM SEGURANÇA DE CONTEXTO)
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
    usuario_dono: str


class LoteMedicamentoSchema(BaseModel):
    medicamento_id: int
    numero_lote: str
    fabricante: str
    data_fabricacao: Optional[str] = None
    validade: str
    quantidade: int = Field(..., gt=0)
    usuario_dono: str


class InsumoSchema(BaseModel):
    nome: str = Field(..., min_length=1)
    especificacao: str
    unidade_medida: str
    grupo: str
    usuario_dono: str


class LoteInsumoSchema(BaseModel):
    insumo_id: int
    numero_lote: str
    fabricante: str
    data_fabricacao: Optional[str] = None
    validade: str
    quantidade: int = Field(..., gt=0)
    usuario_dono: str


class DispensacaoSchema(BaseModel):
    tipo_material: str
    lote_id: int
    quantidade: int = Field(..., gt=0)
    setor_destino: str
    paciente_nome: str
    prescricao_num: str
    responsavel: str
    usuario_dono: str


class TecnovigilanciaSchema(BaseModel):
    lote_suspeito: str
    tipo_ocorrencia: str
    descricao: str
    gravidade: str
    conduta_imediata: str
    operador: str
    usuario_dono: str


class VerificarAdminSchema(BaseModel):
    senha: str


class AktualizarUsuarioSchema(BaseModel):
    usuario: str
    senha: str
    perfil: str


class RegistrarUsuarioSchema(BaseModel):
    usuario: str
    senha: str
    perfil: str


# =====================================================================
# 📊 ROTA DO DASHBOARD & AUDITORIA (FILTRADO POR USUÁRIO)
# =====================================================================
@app.get("/api/dashboard/resumo", tags=["Auditoria Sanitária"])
def obter_resumo_dashboard_vencidos(usuario: str = "admin"):
    db = conectar_bd()
    cursor = db.cursor()
    data_atual = date.today()

    cursor.execute("""
        SELECT med.nome, l.numero_lote, l.validade, l.quantidade 
        FROM lotes l 
        JOIN medicamentos med ON l.medicamento_id = med.id 
        WHERE l.quantidade > 0 AND l.validade <= %s AND l.usuario_dono = %s
    """, (data_atual, usuario))
    lotes_med = cursor.fetchall()

    cursor.execute("""
        SELECT i.nome, li.numero_lote, li.validade, li.quantidade 
        FROM lotes_insumos li 
        JOIN insumos i ON li.insumo_id = i.id 
        WHERE li.quantidade > 0 AND li.validade <= %s AND li.usuario_dono = %s
    """, (data_atual, usuario))
    lotes_ins = cursor.fetchall()
    db.close()

    alertas = []
    for r in lotes_med:
        alertas.append({"tipo": "MEDICAMENTO VENCIDO", "detalhe": f"{r['nome']} (Lote: {r['numero_lote']})", "validade": str(r['validade']), "estoque": r['quantidade']})
    for r in lotes_ins:
        alertas.append({"tipo": "INSUMO VENCIDO", "detalhe": f"{r['nome']} (Lote: {r['numero_lote']})", "validade": str(r['validade']), "estoque": r['quantidade']})

    return {"vencidos": alertas, "total_criticos": len(alertas)}


# =====================================================================
# GERENCIAMENTO DE ACESSOS (ADMINISTRATIVO MASTER)
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
    cursor.execute("""
        UPDATE usuarios 
        SET usuario = %s, senha = %s, perfil = %s 
        WHERE id = %s
    """, (dados.usuario, dados.senha, dados.perfil, usuario_id))
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Dados da unidade atualizados."}


@app.post("/api/auth/verificar-admin", tags=["Autenticação"])
def verificar_senha_master_admin(dados: VerificarAdminSchema):
    senha_env = os.getenv("admin_password") or os.getenv("ADMIN_PASSWORD") or os.getenv("ADMIN_MASTER_PASSWORD")
    senha_master = senha_env.strip() if senha_env else "Mudar@123_Seguro"

    if dados.senha.strip() == senha_master:
        return {"status": "sucesso", "autorizado": True}

    raise HTTPException(status_code=401, detail="Senha Master de Administrador incorreta.")


@app.post("/api/auth/registrar", tags=["Autenticação"])
def registrar_novo_usuario_unidade(dados: RegistrarUsuarioSchema):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO usuarios (usuario, senha, perfil) VALUES (%s, %s, %s)",
            (dados.usuario, dados.senha, dados.perfil)
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
    cursor.execute("SELECT usuario, perfil FROM usuarios WHERE usuario=%s AND senha=%s", (dados.usuario, dados.senha))
    user = cursor.fetchone()
    db.close()

    if user:
        return {"status": "sucesso", "usuario": user["usuario"], "perfil": user["perfil"]}
    raise HTTPException(status_code=401, detail="Credenciais inválidas.")


# =========================================================================
# ENDPOINTS OPERACIONAIS ISOLADOS POR CONTA (MEDICAMENTOS)
# =========================================================================
@app.get("/api/medicamentos", tags=["Medicamentos"])
def listar_medicamentos(usuario: str = "admin"):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id, nome, principio_ativo, categoria, codigo_barras, controlado FROM medicamentos WHERE usuario_dono = %s ORDER BY id DESC", (usuario,))
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/medicamentos", tags=["Medicamentos"])
def cadastrar_medicamento(med: MedicamentoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO medicamentos (nome, principio_ativo, categoria, controlado, codigo_barras, usuario_dono) VALUES (%s,%s,%s,%s,%s,%s)",
            (med.nome, med.principio_ativo, med.categoria, med.controlado, med.codigo_barras, med.usuario_dono)
        )
        db.commit()
    except psycopg2.errors.UniqueViolation:
        db.close()
        raise HTTPException(status_code=400, detail="Este Código de Barras já existe.")
    db.close()
    return {"status": "sucesso", "mensagem": f"Medicamento '{med.nome}' catalogado."}


@app.put("/api/medicamentos/{med_id}", tags=["Medicamentos"])
def atualizar_medicamento(med_id: int, med: MedicamentoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE medicamentos 
        SET nome = %s, principio_ativo = %s, categoria = %s, controlado = %s, codigo_barras = %s
        WHERE id = %s AND usuario_dono = %s
    """, (med.nome, med.principio_ativo, med.categoria, med.controlado, med.codigo_barras, med_id, med.usuario_dono))
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": f"Cadastro do medicamento atualizado."}


@app.get("/api/lotes/medicamentos", tags=["Lotes & Estoque"])
def listar_lotes_medicamentos(usuario: str = "admin"):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT l.id, med.nome as medicamento, l.numero_lote, l.fabricante, l.validade, l.quantidade 
        FROM lotes l JOIN medicamentos med ON l.medicamento_id = med.id
        WHERE l.quantidade > 0 AND l.usuario_dono = %s
    """, (usuario,))
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/lotes/medicamentos", tags=["Lotes & Estoque"])
def receber_lote_medicamento(lote: LoteMedicamentoSchema):
    try:
        data_validade = datetime.strptime(lote.validade, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data de validade inválido. Use AAAA-MM-DD.")

    db = conectar_bd()
    cursor = db.cursor()
    fabricacao = lote.data_fabricacao if lote.data_fabricacao else None

    cursor.execute(
        "INSERT INTO lotes (medicamento_id, numero_lote, fabricante, data_fabricacao, validade, quantidade, usuario_dono) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (lote.medicamento_id, lote.numero_lote, lote.fabricante, fabricacao, data_validade, lote.quantidade, lote.usuario_dono)
    )
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Lote de medicamento incorporado."}


# =========================================================================
# ENDPOINTS OPERACIONAIS ISOLADOS POR CONTA (INSUMOS)
# =========================================================================
@app.get("/api/insumos", tags=["Insumos"])
def listar_insumos(usuario: str = "admin"):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id, nome, especificacao, unidade_medida, grupo FROM insumos WHERE usuario_dono = %s ORDER BY id DESC", (usuario,))
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/insumos", tags=["Insumos"])
def cadastrar_insumo(ins: InsumoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO insumos (nome, especificacao, unidade_medida, grupo, usuario_dono) VALUES (%s, %s, %s, %s, %s)",
        (ins.nome, ins.especificacao, ins.unidade_medida, ins.grupo, ins.usuario_dono)
    )
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": f"Insumo '{ins.nome}' catalogado."}


@app.get("/api/lotes/insumos", tags=["Lotes & Estoque"])
def listar_lotes_insumos(usuario: str = "admin"):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT li.id, i.nome as insumo, li.numero_lote, li.fabricante, li.validade, li.quantidade 
        FROM lotes_insumos li JOIN insumos i ON li.insumo_id = i.id
        WHERE li.quantidade > 0 AND li.usuario_dono = %s
    """, (usuario,))
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/lotes/insumos", tags=["Lotes & Estoque"])
def receber_lote_insumo(lote: LoteInsumoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO lotes_insumos (insumo_id, numero_lote, fabricante, validade, quantidade, usuario_dono) VALUES (%s, %s, %s, %s, %s, %s)",
        (lote.insumo_id, lote.numero_lote, lote.fabricante, lote.validade, lote.quantidade, lote.usuario_dono)
    )
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Lote de insumo incorporado ao inventário."}


# =====================================================================
# ⚡ DISPENSAÇÃO UNIFICADA COM ISOLAMENTO DE TRANSARÇÃO
# =====================================================================
@app.post("/api/dispensacao", tags=["Dispensação unificada"])
def processar_dispensacao(disp: DispensacaoSchema):
    db = conectar_bd()
    cursor = db.cursor()

    try:
        if disp.tipo_material == "MEDICAMENTO":
            cursor.execute("SELECT quantidade FROM lotes WHERE id = %s AND usuario_dono = %s", (disp.lote_id, disp.usuario_dono))
            lote = cursor.fetchone()
            if not lote:
                raise HTTPException(status_code=404, detail="Lote não encontrado para esta unidade.")
            if lote["quantidade"] < disp.quantidade:
                raise HTTPException(status_code=400, detail="Saldo insuficiente no lote de medicamento.")

            cursor.execute("UPDATE lotes SET quantidade = quantidade - %s WHERE id = %s AND usuario_dono = %s", (disp.quantidade, disp.lote_id, disp.usuario_dono))

            cursor.execute("""
                INSERT INTO movimentacoes (lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao, usuario_dono)
                VALUES (%s, NULL, 'SAÍDA MEDICAMENTO', %s, %s, %s, %s, %s, %s, %s)
            """, (disp.lote_id, disp.quantidade, disp.setor_destino, disp.paciente_nome, disp.prescricao_num, disp.responsavel, datetime.now().strftime("%Y-%m-%d %H:%M"), disp.usuario_dono))

        elif disp.tipo_material == "INSUMO":
            cursor.execute("SELECT quantidade FROM lotes_insumos WHERE id = %s AND usuario_dono = %s", (disp.lote_id, disp.usuario_dono))
            lote = cursor.fetchone()
            if not lote or lote["quantidade"] < disp.quantidade:
                raise HTTPException(status_code=400, detail="Saldo insuficiente no lote de insumo.")

            cursor.execute("UPDATE lotes_insumos SET quantidade = quantidade - %s WHERE id = %s AND usuario_dono = %s", (disp.quantidade, disp.lote_id, disp.usuario_dono))
            
            cursor.execute("""
                INSERT INTO movimentacoes (lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao, usuario_dono)
                VALUES (NULL, %s, 'SAÍDA INSUMO', %s, %s, %s, %s, %s, %s, %s)
            """, (disp.lote_id, disp.quantidade, disp.setor_destino, disp.paciente_nome, disp.prescricao_num, disp.responsavel, datetime.now().strftime("%Y-%m-%d %H:%M"), disp.usuario_dono))

        db.commit()
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Erro interno na transação: {str(e)}")
    finally:
        db.close()

    return {"status": "sucesso", "mensagem": "Dispensação processada com sucesso!"}


@app.get("/api/auditoria/movimentacoes", tags=["Auditoria & Compliance"])
def relatorio_rastreabilidade(usuario: str = "admin"):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao 
        FROM movimentacoes 
        WHERE usuario_dono = %s
        ORDER BY id DESC
    """, (usuario,))
    rows = cursor.fetchall()
    db.close()
    return rows


# =====================================================================
# ⚠️ TECNOVIGILÂNCIA ISOLADA POR CONTEXTO HOSPITALAR
# =====================================================================
@app.post("/api/tecnovigilancia", tags=["Tecnovigilância (POP.FARM.019)"])
def registrar_ocorrencia(event: TecnovigilanciaSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO tecnovigilancia (lote_texto, tipo_ocorrencia, descricao, gravidade, conduta, data_registro, operador, usuario_dono)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        event.lote_suspeito,
        event.tipo_ocorrencia,
        event.descricao,
        event.gravidade,
        event.conduta_imediata,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        event.operador,
        event.usuario_dono
    ))
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Ocorrência sanitária protocolada."}


@app.get("/api/tecnovigilancia", tags=["Tecnovigilância (POP.FARM.019)"])
def listar_ocorrencias_tecnovigilancia(usuario: str = "admin"):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, lote_texto AS lote_suspeito, tipo_ocorrencia, gravidade, data_registro, operador 
        FROM tecnovigilancia 
        WHERE usuario_dono = %s
        ORDER BY id DESC
    """, (usuario,))
    rows = cursor.fetchall()
    db.close()
    return rows


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
