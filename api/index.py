# Adicione este schema de validação logo abaixo dos seus outros Schemas no app.py
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

# ⚠️ COLE AQUI A SUA STRING DE CONEXÃO DO NEON
# Exemplo: "postgresql://usuario:senha@ep-xyz-123.us-east-1.aws.neon.tech/neondb?sslmode=require"
DATABASE_URL = os.getenv("DATABASE_URL")


def conectar_bd():
    try:
        # Abre a conexão segura com o Neon usando a sua string
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

        # 🛠️ CRIAÇÃO AUTOMÁTICA DA TABELA PARA O ADMIN.HTML
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                usuario VARCHAR(150) UNIQUE NOT NULL,
                senha VARCHAR(255) NOT NULL,
                perfil VARCHAR(150) NOT NULL
            );
        """)
        conn.commit()  # Salva a estrutura no banco de dados
        cursor.close()

        return conn
    except Exception as e:
        print(f"❌ ERRO CRÍTICO DE CONEXÃO COM O POSTGRESQL: {str(e)}")
        raise e

                
def conectar_bd():
    try:
        # sslmode=require é obrigatório para conexões seguras com o Neon
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao conectar ao PostgreSQL na nuvem: {str(e)}")


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

# Adicione este schema de validação logo abaixo dos seus outros Schemas no app.py

class VerificarAdminSchema(BaseModel):
    senha: str


# --- NOVAS ROTAS PARA GERENCIAMENTO COMPLETO DE CLIENTES/UNIDADES ---

@app.delete("/api/auth/usuarios/{usuario_id}", tags=["Autenticação"])
def deletar_usuario_unidade(usuario_id: int):
    db = conectar_bd()
    cursor = db.cursor()

    # Executa a exclusão pelo ID único
    cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
    db.commit()
    db.close()

    return {"status": "sucesso", "mensagem": "Unidade/Acesso revogado com sucesso."}


class AtualizarUsuarioSchema(BaseModel):
    usuario: str
    senha: str
    perfil: str


@app.put("/api/auth/usuarios/{usuario_id}", tags=["Autenticação"])
def atualizar_usuario_unidade(usuario_id: int, dados: AtualizarUsuarioSchema):
    db = conectar_bd()
    cursor = db.cursor()

    # Atualiza os dados da unidade cadastrada
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
    # Procura a variável configurada no painel da Vercel
    # Se não configurada, assume um fallback seguro ou impede o acesso
    senha_master = os.getenv("ADMIN_MASTER_PASSWORD", "Mudar@123_Seguro")

    if dados.senha == senha_master:
        return {"status": "sucesso", "autorizado": True}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Senha Master de Administrador incorreta."
    )

class RegistrarUsuarioSchema(BaseModel):
    usuario: str
    senha: str
    perfil: str

# ROTA 1: Para o admin.html registrar novos clientes/unidades no PostgreSQL
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

# ROTA 2: Para o admin.html listar os acessos já existentes na tabela
@app.get("/api/auth/usuarios", tags=["Autenticação"])
def listar_usuarios_unidades():
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id, usuario, perfil FROM usuarios ORDER BY id DESC")
    rows = cursor.fetchall()
    db.close()
    return rows


# =========================================================================
# ENDPOINTS (SINTAXE DO POSTGRESQL COM %s)
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
        datetime.now().strftime("%Y-%m-%d %H:%M")))

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
        datetime.now().strftime("%Y-%m-%d %H:%M")))
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
    data_atual = datetime.now().date()  # PostgreSQL trata objetos Date nativos perfeitamente
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
        event.tipo_ocorrencia,  # 💻 CORRIGIDO: Removido o 'r' incorreto (era tipo_orcorrencia)
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
