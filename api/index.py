import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor  # Mantém o acesso às colunas por nome

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


# 🛠️ CORRIGIDO: Removida a duplicidade. Esta função agora gerencia a conexão E garante a estrutura do banco.
def conectar_bd():
    try:
        # Abre a conexão segura com o Neon (sslmode=require é implícito ou adicionado na string)
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

        # 2. TABELA DE MEDICAMENTOS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS medicamentos (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                principio_ativo VARCHAR(255) NOT NULL,
                categoria VARCHAR(150) NOT NULL,
                controlado INT NOT NULL,
                codigo_barras VARCHAR(150) UNIQUE
            );
        """)

        # 3. TABELA DE LOTES DE MEDICAMENTOS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lotes (
                id SERIAL PRIMARY KEY,
                medicamento_id INT REFERENCES medicamentos(id) ON DELETE CASCADE,
                numero_lote VARCHAR(150) NOT NULL,
                fabricante VARCHAR(255) NOT NULL,
                data_fabricacao DATE NOT NULL,
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
                grupo VARCHAR(150) NOT NULL
            );
        """)

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
                data_movimentacao VARCHAR(50) NOT NULL
            );
        """)

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
                operador VARCHAR(255) NOT NULL
            );
        """)

        conn.commit()  # Salva todas as estruturas de tabelas no banco de dados
        cursor.close()
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao conectar ou estruturar o PostgreSQL na nuvem: {str(e)}")


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
    controlado: int  # 0 para Não, 1 para Sim
    codigo_barras: Optional[str] = "Nenhum"


class LoteMedicamentoSchema(BaseModel):
    medicamento_id: int
    numero_lote: str
    fabricante: str
    data_fabricacao: str  # YYYY-MM-DD
    validade: str  # YYYY-MM-DD
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
    validade: str  # YYYY-MM-DD
    quantidade: int = Field(..., gt=0)


class DispensacaoSchema(BaseModel):
    tipo_material: str  # "MEDICAMENTO" ou "INSUMO"
    lote_id: int
    quantidade: int = Field(..., gt=0)
    setor_destino: str
    paciente_nome: str
    prescricao_num: str
    responsavel: str


class TecnovigilanciaSchema(BaseModel):
    lote_texto: str
    tipo_ocorrencia: str
    descricao: str
    gravidade: str
    conduta: str
    operador: str


class VerificarAdminSchema(BaseModel):
    senha: str


class AtualizarUsuarioSchema(BaseModel):
    usuario: str
    senha: str
    perfil: str


class RegistrarUsuarioSchema(BaseModel):
    usuario: str
    senha: str
    perfil: str


# =====================================================================
# 📊 ROTA DO DASHBOARD (INDICADORES EM TEMPO REAL)
# =====================================================================
@app.get("/api/dashboard/resumo", tags=["Dashboard"])
def obter_resumo_dashboard():
    db = conectar_bd()
    cursor = db.cursor()
    
    # Total de Medicamentos Distintos
    cursor.execute("SELECT COUNT(*) AS total FROM medicamentos")
    meds = cursor.fetchone()["total"]
    
    # Total de Insumos Distintos
    cursor.execute("SELECT COUNT(*) AS total FROM insumos")
    insumos = cursor.fetchone()["total"]
    
    # Quantidade de itens com estoque zerado ou abaixo do mínimo
    cursor.execute("SELECT COUNT(*) AS total FROM lotes_medicamentos WHERE quantidade <= 0")
    Críticos_med = cursor.fetchone()["total"]
    
    # Total de alertas de vencimento (vencidos ou vencendo em 60 dias)
    from datetime import date, timedelta
    data_limite = date.today() + timedelta(days=60)
    
    cursor.execute("SELECT COUNT(*) AS total FROM lotes_medicamentos WHERE validade <= %s AND quantidade > 0", (data_limite,))
    vencendo_med = cursor.fetchone()["total"]
    
    db.close()
    
    return {
        "total_medicamentos": meds,
        "total_insumos": insumos,
        "estoque_critico": Críticos_med,
        "alertas_vencimento": vencendo_med
    }

# =====================================================================
# 📥 ROTAS DE MOVIMENTAÇÃO: ENTRADA DE LOTES
# =====================================================================
class EntradaLoteSchema(BaseModel):
    item_id: int
    tipo: str  # "MEDICAMENTO" ou "INSUMO"
    numero_lote: str
    quantidade: int
    validade: str
    fabricante: Optional[str] = "Não Informado"
    preco_unitario: Optional[float] = 0.0

@app.post("/api/movimentacao/entrada", tags=["Movimentação de Estoque"])
def registrar_entrada_lote(lote: EntradaLoteSchema):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        tabela = "lotes_medicamentos" if lote.tipo == "MEDICAMENTO" else "lotes_insumos"
        coluna_id = "medicamento_id" if lote.tipo == "MEDICAMENTO" else "insumo_id"
        
        cursor.execute(f"""
            INSERT INTO {tabela} ({coluna_id}, numero_lote, quantidade, validade, fabricante, preco_unitario)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (lote.item_id, lote.numero_lote, lote.quantidade, lote.validade, lote.fabricante, lote.preco_unitario))
        
        db.commit()
        return {"status": "success", "message": "Lote inserido e estoque atualizado com sucesso!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao inserir lote: {str(e)}")
    finally:
        db.close()

# =====================================================================
# 📤 ROTAS DE MOVIMENTAÇÃO: DISTRIBUIÇÃO (SAÍDA PARA SETORES)
# =====================================================================
class SaidaEstoqueSchema(BaseModel):
    lote_id: int
    tipo: str  # "MEDICAMENTO" ou "INSUMO"
    quantidade_saida: int
    destino_setor: str
    operador: str

@app.post("/api/movimentacao/saida", tags=["Movimentação de Estoque"])
def registrar_saida_estoque(saida: SaidaEstoqueSchema):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        tabela = "lotes_medicamentos" if saida.tipo == "MEDICAMENTO" else "lotes_insumos"
        
        # Verificar se há estoque disponível no lote
        cursor.execute(f"SELECT quantidade, numero_lote FROM {tabela} WHERE id = %s", (saida.lote_id,))
        lote_atual = cursor.fetchone()
        
        if not lote_atual or lote_atual["quantidade"] < saida.quantidade_saida:
            raise HTTPException(status_code=400, detail="Quantidade insuficiente em estoque para este lote específico.")
        
        # Baixar estoque do lote
        cursor.execute(f"UPDATE {tabela} SET quantidade = quantidade - %s WHERE id = %s", 
                       (saida.quantidade_saida, saida.lote_id))
        
        # Registrar no histórico global de movimentações (Opcional, mas altamente recomendado para auditoria)
        cursor.execute("""
            INSERT INTO tecnovigilancia (lote_texto, tipo_ocorrencia, descricao, gravidade, conduta, data_registro, operador)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (lote_atual["numero_lote"], "DISTRIBUIÇÃO INTERNA", f"Saída de {saida.quantidade_saida} unidades para {saida.destino_setor}", "Informativo", "Estoque Baixado", datetime.now().date(), saida.operador))
        
        db.commit()
        return {"status": "success", "message": "Distribuição realizada com sucesso e lote atualizado!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

# --- ROTAS PARA GERENCIAMENTO COMPLETO DE CLIENTES/UNIDADES ---

@app.delete("/api/auth/usuarios/{usuario_id}", tags=["Autenticação"])
def deletar_usuario_unidade(usuario_id: int):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Unidade/Acesso revogado com sucesso."}


@app.put("/api/auth/usuarios/{usuario_id}", tags=["Autenticação"])
def atualizar_usuario_unidade(usuario_id: int, dados: AtualizarUsuarioSchema):
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
    # 🔒 Tenta ler em minúsculas (padrão atual) ou em maiúsculas (padrão comum de servidores)
    senha_env = os.getenv("admin_password") or os.getenv("ADMIN_PASSWORD") or os.getenv("ADMIN_MASTER_PASSWORD")

    if senha_env:
        senha_master = senha_env.strip()
    else:
        senha_master = "Mudar@123_Seguro"

    if dados.senha.strip() == senha_master:
        return {"status": "sucesso", "autorizado": True}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Senha Master de Administrador incorreta."
    )

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


# =========================================================================
# ENDPOINTS OPERACIONAIS
# =========================================================================

@app.post("/api/auth/login", tags=["Autenticação"])
def login(dados: LoginSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT usuario, perfil FROM usuarios WHERE usuario=%s AND senha=%s", (dados.usuario, dados.senha))
    user = cursor.fetchone()
    db.close()

    if user:
        return {"status": "sucesso", "usuario": user["usuario"], "perfil": user["perfil"]}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas.")


@app.get("/api/medicamentos", tags=["Medicamentos"])
def listar_medicamentos():
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id, nome, principio_ativo, categoria, codigo_barras, controlado FROM medicamentos")
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/medicamentos", tags=["Medicamentos"])
def cadastrar_medicamento(med: MedicamentoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO medicamentos (nome, principio_ativo, categoria, controlado, codigo_barras) VALUES (%s,%s,%s,%s,%s)",
            (med.nome, med.principio_ativo, med.categoria, med.controlado, med.codigo_barras)
        )
        db.commit()
    except psycopg2.errors.UniqueViolation:
        db.close()
        raise HTTPException(status_code=400, detail="Este Código de Barras já existe.")
    db.close()
    return {"status": "sucesso", "mensagem": f"Medicamento '{med.nome}' catalogado."}


@app.get("/api/lotes/medicamentos", tags=["Lotes & Estoque"])
def listar_lotes_medicamentos():
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT l.id, med.nome as medicamento, l.numero_lote, l.fabricante, l.validade, l.quantidade 
        FROM lotes l JOIN medicamentos med ON l.medicamento_id = med.id
    """)
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/lotes/medicamentos", tags=["Lotes & Estoque"])
def receber_lote_medicamento(lote: LoteMedicamentoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO lotes (medicamento_id, numero_lote, fabricante, data_fabricacao, validade, quantidade) VALUES (%s,%s,%s,%s,%s,%s)",
        (lote.medicamento_id, lote.numero_lote, lote.fabricante, lote.data_fabricacao, lote.validade, lote.quantidade)
    )
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Lote de medicamento incorporado ao inventário."}


@app.get("/api/insumos", tags=["Insumos"])
def listar_insumos():
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id, nome, especificacao, unidade_medida, grupo FROM insumos")
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/insumos", tags=["Insumos"])
def cadastrar_insumo(ins: InsumoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO insumos (nome, especificacao, unidade_medida, grupo) VALUES (%s, %s, %s, %s)",
        (ins.nome, ins.especificacao, ins.unidade_medida, ins.grupo)
    )
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": f"Insumo '{ins.nome}' catalogado."}


@app.get("/api/lotes/insumos", tags=["Lotes & Estoque"])
def listar_lotes_insumos():
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT li.id, i.nome as insumo, li.numero_lote, li.fabricante, li.validade, li.quantidade 
        FROM lotes_insumos li JOIN insumos i ON li.insumo_id = i.id
    """)
    rows = cursor.fetchall()
    db.close()
    return rows


@app.post("/api/lotes/insumos", tags=["Lotes & Estoque"])
def receber_lote_insumo(lote: LoteInsumoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO lotes_insumos (insumo_id, numero_lote, fabricante, validade, quantidade) VALUES (%s, %s, %s, %s, %s)",
        (lote.insumo_id, lote.numero_lote, lote.fabricante, lote.validade, lote.quantidade)
    )
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Lote de insumo incorporado ao inventário."}


@app.post("/api/dispensacao", tags=["Dispensação unificada"])
def processar_dispensacao(disp: DispensacaoSchema):
    db = conectar_bd()
    cursor = db.cursor()

    if disp.tipo_material == "MEDICAMENTO":
        cursor.execute("SELECT quantidade FROM lotes WHERE id = %s", (disp.lote_id,))
        lote = cursor.fetchone()
        if not lote or lote["quantidade"] < disp.quantidade:
            db.close()
            raise HTTPException(status_code=400, detail="Saldo insuficiente no lote de medicamento.")

        cursor.execute("UPDATE lotes SET quantidade = quantidade - %s WHERE id = %s", (disp.quantidade, disp.lote_id))
        cursor.execute("""
            INSERT INTO movimentacoes (lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao)
            VALUES (%s, NULL, 'SAÍDA MEDICAMENTO', %s, %s, %s, %s, %s, %s)
        """, (
            disp.lote_id, disp.quantidade, disp.setor_destino, disp.paciente_nome, disp.prescricao_num, disp.responsavel,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

    elif disp.tipo_material == "INSUMO":
        cursor.execute("SELECT quantidade FROM lotes_insumos WHERE id = %s", (disp.lote_id,))
        lote = cursor.fetchone()
        if not lote or lote["quantidade"] < disp.quantidade:
            db.close()
            raise HTTPException(status_code=400, detail="Saldo insuficiente no lote de insumo.")

        cursor.execute("UPDATE lotes_insumos SET quantidade = quantidade - %s WHERE id = %s",
                       (disp.quantidade, disp.lote_id))
        cursor.execute("""
            INSERT INTO movimentacoes (lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao)
            VALUES (NULL, %s, 'SAÍDA INSUMO', %s, %s, %s, %s, %s, %s)
        """, (
            disp.lote_id, disp.quantidade, disp.setor_destino, disp.paciente_nome, disp.prescricao_num, disp.responsavel,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))
    else:
        db.close()
        raise HTTPException(status_code=400, detail="Tipo de material desconhecido.")

    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Dispensação processada."}


@app.get("/api/auditoria/movimentacoes", tags=["Auditoria & Compliance"])
def relatorio_rastreabilidade():
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute(
        "SELECT id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao FROM movimentacoes ORDER BY id DESC")
    rows = cursor.fetchall()
    db.close()
    return rows


@app.get("/api/auditoria/alertas", tags=["Auditoria & Compliance"])
def verificar_alertas_sanitarios():
    data_atual = datetime.now().date()
    db = conectar_bd()
    cursor = db.cursor()

    cursor.execute(
        "SELECT m.nome, l.numero_lote, l.validade, l.quantidade FROM lotes l JOIN medicamentos m ON l.medicamento_id = m.id WHERE l.quantidade > 0 AND l.validade <= %s",
        (data_atual,))
    lotes_med = cursor.fetchall()

    cursor.execute(
        "SELECT i.nome, li.numero_lote, li.validade, li.quantidade FROM lotes_insumos li JOIN insumos i ON li.insumo_id = i.id WHERE li.quantidade > 0 AND li.validade <= %s",
        (data_atual,))
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
def registrar_ocorrencia(event: TecnovigilanciaSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO tecnovigilancia (lote_texto, tipo_ocorrencia, descricao, gravidade, conduta, data_registro, operador)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        event.lote_texto,
        event.tipo_ocorrencia,
        event.descricao,
        event.gravidade,
        event.conduta,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        event.operador
    ))
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Ocorrência sanitária protocolada."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
