import os
import sqlite3
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, status, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# =====================================================================
# ⚙️ CONFIGURAÇÃO DA API & CORS
# =====================================================================
app = FastAPI(
    title="Sistema de Gestão de Farmácia Hospitalar & Tecnovigilância",
    description="API sincronizada em tempo real para controle de estoque, dispensação fracionada e auditorias.",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_NAME = "farmacia_hospitalar.db"

def conectar_bd():
    conn = sqlite3.connect(DATABASE_NAME)
    # Permite acessar colunas por nome como se fosse um dicionário dict (ex: row['nome'])
    conn.row_factory = sqlite3.Row
    return conn

# =====================================================================
# 📋 SCHEMAS DE VALIDAÇÃO DE DADOS (PYDANTIC)
# =====================================================================

class LoginRequest(BaseModel):
    usuario: str
    senha: str

class MedicamentoSchema(BaseModel):
    nome: str
    principio_ativo: str
    categoria: str
    codigo_barras: Optional[str] = "Nenhum"
    controlado: int = Field(0, description="0 para Não, 1 para Sim")

class LoteMedicamentoSchema(BaseModel):
    medicamento_id: int
    numero_lote: str
    fabricante: str
    validade: str  # Recebe a string YYYY-MM-DD do input de data do HTML
    quantidade: int

class InsumoSchema(BaseModel):
    nome: str
    especificacao: Optional[str] = "Nenhum"
    unidade_medida: str
    grupo: str

class LoteInsumoSchema(BaseModel):
    insumo_id: int
    numero_lote: str
    fabricante: str
    validade: str  # Recebe a string YYYY-MM-DD do input de data do HTML
    quantidade: int

class DispensacaoSchema(BaseModel):
    tipo_material: str = Field(..., description="MEDICAMENTO ou INSUMO")
    lote_id: int
    quantidade: int
    setor_destino: str
    paciente_nome: Optional[str] = "Uso Geral"
    prescricao_num: Optional[str] = "Nenhum"
    responsavel: str

class TecnovigilanciaSchema(BaseModel):
    lote_suspeito: str
    tipo_ocorrencia: str
    gravidade: str
    conduta_imediata: str
    descricao: str
    operador: str

# =====================================================================
# 🔒 ROTAS DE AUTENTICAÇÃO
# =====================================================================

@app.post("/api/auth/login", tags=["Autenticação"])
def login(dados: LoginRequest):
    # Simulação robusta de banco de usuários para isolamento de dados de perfis
    usuarios_validos = {
        "admin": {"perfil": "Administrador Master"},
        "farmaceutico_dia": {"perfil": "Farmacêutico Plantonista (Dia)"},
        "farmaceutico_noite": {"perfil": "Farmacêutico Plantonista (Noite)"},
        "tecnico_enfermagem": {"perfil": "Técnico de Enfermagem Coletor"}
    }
    
    usuario_normalizado = dados.usuario.strip().lower()
    if usuario_normalizado in usuarios_validos and dados.senha == "123456":
        return {
            "status": "sucesso",
            "usuario": dados.usuario,
            "perfil": usuarios_validos[usuario_normalizado]["perfil"]
        }
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="❌ Usuário ou senha incorretos."
    )

# =====================================================================
# 💊 MÓDULO MEDICAMENTOS (BASE & LOTES)
# =====================================================================

@app.get("/api/medicamentos", tags=["Medicamentos"])
def listar_medicamentos():
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id, nome, principio_ativo, categoria, codigo_barras, controlado FROM medicamentos ORDER BY nome ASC")
    meds = [dict(row) for row in cursor.fetchall()]
    db.close()
    return meds

@app.post("/api/medicamentos", status_code=status.HTTP_201_CREATED, tags=["Medicamentos"])
def cadastrar_medicamento(med: MedicamentoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO medicamentos (nome, principio_ativo, categoria, codigo_barras, controlado)
            VALUES (%s, %s, %s, %s, %s)
        """.replace("%s", "?"), (med.nome, med.principio_ativo, med.categoria, med.codigo_barras, med.controlado))
        db.commit()
        novo_id = cursor.lastrowid
        db.close()
        return {"status": "sucesso", "id": novo_id}
    except Exception as e:
        db.close()
        raise HTTPException(status_code=400, detail=f"Erro ao cadastrar: {str(e)}")

@app.put("/api/medicamentos/{med_id}", tags=["Medicamentos"])
def atualizar_medicamento(med_id: int, med: MedicamentoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM medicamentos WHERE id = ?", (med_id,))
    if not cursor.fetchone():
        db.close()
        raise HTTPException(status_code=404, detail="Medicamento não encontrado para atualização.")
    
    cursor.execute("""
        UPDATE medicamentos 
        SET nome = ?, principio_ativo = ?, categoria = ?, codigo_barras = ?, controlado = ?
        WHERE id = ?
    """, (med.nome, med.principio_ativo, med.categoria, med.codigo_barras, med.controlado, med_id))
    db.commit()
    db.close()
    return {"status": "atualizado", "id": med_id}

@app.get("/api/lotes/medicamentos", tags=["Medicamentos - Lotes"])
def listar_lotes_medicamentos():
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT l.id, m.nome AS medicamento, l.numero_lote, l.fabricante, l.validade, l.quantidade
        FROM lotes_medicamentos l
        JOIN medicamentos m ON l.medicamento_id = m.id
        WHERE l.quantidade >= 0
        ORDER BY l.validade ASC
    """)
    lotes = [dict(row) for row in cursor.fetchall()]
    db.close()
    return lotes

@app.post("/api/lotes/medicamentos", status_code=status.HTTP_201_CREATED, tags=["Medicamentos - Lotes"])
def cadastrar_lote_medicamento(lote: LoteMedicamentoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM medicamentos WHERE id = ?", (lote.medicamento_id,))
    if not cursor.fetchone():
        db.close()
        raise HTTPException(status_code=404, detail="Medicamento de referência não localizado.")
        
    cursor.execute("""
        INSERT INTO lotes_medicamentos (medicamento_id, numero_lote, fabricante, validade, quantidade)
        VALUES (?, ?, ?, ?, ?)
    """, (lote.medicamento_id, lote.numero_lote, lote.fabricante, lote.validade, lote.quantidade))
    db.commit()
    db.close()
    return {"status": "lote_vinculado"}

# =====================================================================
# 📦 MÓDULO INSUMOS (BASE & LOTES)
# =====================================================================

@app.get("/api/insumos", tags=["Insumos Hospitalares"])
def listar_insumos():
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id, nome, especificacao, unidade_medida, grupo FROM insumos ORDER BY nome ASC")
    insumos = [dict(row) for row in cursor.fetchall()]
    db.close()
    return insumos

@app.post("/api/insumos", status_code=status.HTTP_201_CREATED, tags=["Insumos Hospitalares"])
def cadastrar_insumo(ins: InsumoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO insumos (nome, especificacao, unidade_medida, grupo)
        VALUES (?, ?, ?, ?)
    """, (ins.nome, ins.especificacao, ins.unidade_medida, ins.grupo))
    db.commit()
    novo_id = cursor.lastrowid
    db.close()
    return {"status": "sucesso", "id": novo_id}

@app.get("/api/lotes/insumos", tags=["Insumos Hospitalares - Lotes"])
def listar_lotes_insumos():
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("""
        SELECT li.id, i.nome AS insumo, li.numero_lote, li.fabricante, li.validade, li.quantidade
        FROM lotes_insumos li
        JOIN insumos i ON li.insumo_id = i.id
        WHERE li.quantidade >= 0
        ORDER BY li.validade ASC
    """)
    lotes = [dict(row) for row in cursor.fetchall()]
    db.close()
    return lotes

@app.post("/api/lotes/insumos", status_code=status.HTTP_201_CREATED, tags=["Insumos Hospitalares - Lotes"])
def cadastrar_lote_insumo(lote: LoteInsumoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM insumos WHERE id = ?", (lote.insumo_id,))
    if not cursor.fetchone():
        db.close()
        raise HTTPException(status_code=404, detail="Insumo de referência não localizado.")
        
    cursor.execute("""
        INSERT INTO lotes_insumos (insumo_id, numero_lote, fabricante, validade, quantidade)
        VALUES (?, ?, ?, ?, ?)
    """, (lote.insumo_id, lote.numero_lote, lote.fabricante, lote.validade, lote.quantidade))
    db.commit()
    db.close()
    return {"status": "lote_insumo_vinculado"}

# =====================================================================
# ⚡ MÓDULO DISPENSAÇÃO UNIFICADA E CRÍTICA
# =====================================================================

@app.post("/api/dispensacao", tags=["Dispensação e Baixas de Estoque"])
def processar_dispensacao(disp: DispensacaoSchema):
    db = conectar_bd()
    cursor = db.cursor()
    
    tabela_lote = "lotes_medicamentos" if disp.tipo_material.upper() == "MEDICAMENTO" else "lotes_insumos"
    
    # 1. Verifica disponibilidade real de estoque físico
    cursor.execute(f"SELECT quantidade FROM {tabela_lote} WHERE id = ?", (disp.lote_id,))
    resultado_lote = cursor.fetchone()
    
    if not resultado_lote:
        db.close()
        raise HTTPException(status_code=404, detail="O lote selecionado não existe ou foi baixado do sistema.")
        
    estoque_atual = resultado_lote["quantidade"]
    if estoque_atual < disp.quantidade:
        db.close()
        raise HTTPException(status_code=422, detail=f"Estoque insuficiente. Quantidade disponível: {estoque_atual}")
        
    # 2. Executa a baixa de estoque decrementando a quantidade informada
    novo_estoque = estoque_atual - disp.quantidade
    cursor.execute(f"UPDATE {tabela_lote} SET quantidade = ? WHERE id = ?", (novo_estoque, disp.lote_id))
    
    # 3. Grava o histórico na tabela de movimentações com os dados completos solicitados pelo Frontend
    data_hoje = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO movimentacoes (tipo_material, lote_id, quantidade, setor_destino, paciente_nome, responsavel, data_movimentacao)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (disp.tipo_material.upper(), disp.lote_id, disp.quantidade, disp.setor_destino, disp.paciente_nome, disp.responsavel, data_hoje))
    
    db.commit()
    db.close()
    return {"status": "sucesso", "mensagem": "Dispensação homologada com sucesso!", "estoque_restante": novo_estoque}

# =====================================================================
# 🔍 MÓDULO AUDITORIA, RASTREABILIDADE E ISOLAMENTO DE DADOS
# =====================================================================

@app.get("/api/auditoria/movimentacoes", tags=["Auditoria & Rastreabilidade"])
def listar_movimentacoes(operador: Optional[str] = Query(None, description="Filtra e isola dados por usuário logado")):
    db = conectar_bd()
    cursor = db.cursor()
    
    # ISOLAMENTO DE PERFIL: Se o operador for passado, limita os dados para impedir cruzamento indevido
    if operador:
        cursor.execute("""
            SELECT id, tipo_material, lote_id, quantidade, setor_destino, paciente_nome, responsavel, data_movimentacao 
            FROM movimentacoes 
            WHERE responsavel = ?
            ORDER BY id DESC
        """, (operador,))
    else:
        cursor.execute("""
            SELECT id, tipo_material, lote_id, quantidade, setor_destino, paciente_nome, responsavel, data_movimentacao 
            FROM movimentacoes 
            ORDER BY id DESC
        """)
        
    movs = [dict(row) for row in cursor.fetchall()]
    db.close()
    return movs

@app.get("/api/auditoria/alertas", tags=["Auditoria & Rastreabilidade"])
def processar_alertas_sanitarios():
    """Valida prazos de validade em tempo real cruzando a data atual do servidor."""
    db = conectar_bd()
    cursor = db.cursor()
    
    data_atual_str = date.today().isoformat() # Formato YYYY-MM-DD
    
    # Busca medicamentos vencidos
    cursor.execute("""
        SELECT m.nome, l.numero_lote, l.validade 
        FROM lotes_medicamentos l
        JOIN medicamentos m ON l.medicamento_id = m.id
        WHERE l.validade < ? AND l.quantidade > 0
    """, (data_atual_str,))
    meds_vencidos = cursor.fetchall()
    
    alertas_formatados = []
    for item in meds_vencidos:
        alertas_formatados.append({
            "tipo": "MEDICAMENTO",
            "detalhe": f"{item['nome']} (Lote: {item['numero_lote']})",
            "validade": item["validade"]
        })
        
    db.close()
    return {
        "total_criticos": len(alertas_formatados),
        "vencidos": alertas_formatados
    }

# =====================================================================
# ⚠️ MÓDULO TECNOVIGILÂNCIA E SEGURANÇA DO PACIENTE
# =====================================================================

@app.get("/api/tecnovigilancia", tags=["Tecnovigilância (POP.FARM.019)"])
def listar_ocorrencias_tecnovigilancia(operador: Optional[str] = Query(None, description="Isola queixas por perfil logado")):
    db = conectar_bd()
    cursor = db.cursor()
    
    # ISOLAMENTO DE PERFIL: Filtra ocorrências pelo técnico/farmacêutico que as abriu
    if operador:
        cursor.execute("""
            SELECT id, lote_texto AS lote_suspeito, tipo_ocorrencia, descricao, gravidade, conduta AS conduta_imediata, data_registro, operador 
            FROM tecnovigilancia 
            WHERE operador = ?
            ORDER BY id DESC
        """, (operador,))
    else:
        cursor.execute("""
            SELECT id, lote_texto AS lote_suspeito, tipo_ocorrencia, descricao, gravidade, conduta AS conduta_imediata, data_registro, operador 
            FROM tecnovigilancia 
            ORDER BY id DESC
        """)
        
    ocorrencias = [dict(row) for row in cursor.fetchall()]
    db.close()
    return ocorrencias

@app.post("/api/tecnovigilancia", status_code=status.HTTP_201_CREATED, tags=["Tecnovigilância (POP.FARM.019)"])
def registrar_ocorrencia_tecnovigilancia(oc: TecnovigilanciaSchema):
    db = conectar_bd()
    cursor = db.cursor()
    
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO tecnovigilancia (lote_texto, tipo_ocorrencia, descricao, gravidade, conduta, data_registro, operador)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (oc.lote_suspeito, oc.tipo_ocorrencia, oc.descricao, oc.gravidade, oc.conduta_imediata, data_atual, oc.operador))
    
    db.commit()
    db.close()
    return {"status": "notificado", "mensagem": "Ocorrência enviada ao Núcleo de Segurança do Paciente."}
