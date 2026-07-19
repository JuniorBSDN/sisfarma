import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date
import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field
from typing import Optional

app = FastAPI(
    title="sisFarma API - Central CAF & Rastreabilidade Hospitalar",
    description="Backend em nuvem compatível com o painel operacional do dia 16",
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

# 🛠️ GERENCIADOR DE CONEXÃO E CRIAÇÃO AUTOMÁTICA DE TABELAS
def conectar_bd():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Tabela de Colaboradores / Operadores (Compatível com Login por CPF/Crachá)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS colaboradores (
                id SERIAL PRIMARY KEY,
                cpf VARCHAR(11) UNIQUE NOT NULL,
                nome VARCHAR(255) NOT NULL,
                cargo VARCHAR(150) NOT NULL,
                empresa_cnpj VARCHAR(14) NOT NULL
            );
        """)

        # Tabela de Administradores Locais (Compatível com admin.html)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS administradores (
                id SERIAL PRIMARY KEY,
                cnpj VARCHAR(14) UNIQUE NOT NULL,
                senha VARCHAR(255) NOT NULL,
                hospital_nome VARCHAR(255) NOT NULL
            );
        """)

        # Tabela de Medicamentos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS medicamentos (
                id SERIAL PRIMARY KEY,
                empresa_cnpj VARCHAR(14) NOT NULL,
                nome VARCHAR(255) NOT NULL,
                principio_ativo VARCHAR(255) NOT NULL,
                categoria VARCHAR(150) NOT NULL,
                controlado INT NOT NULL DEFAULT 0,
                codigo_barras VARCHAR(150)
            );
        """)

        # Tabela de Lotes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lotes (
                id SERIAL PRIMARY KEY,
                medicamento_id INT REFERENCES medicamentos(id) ON DELETE CASCADE,
                numero_lote VARCHAR(150) NOT NULL,
                fabricante VARCHAR(255) NOT NULL,
                validade DATE NOT NULL,
                quantidade INT NOT NULL
            );
        """)

        # Tabela de Insumos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insumos (
                id SERIAL PRIMARY KEY,
                empresa_cnpj VARCHAR(14) NOT NULL,
                nome VARCHAR(255) NOT NULL,
                especificacao TEXT,
                unidade_medida VARCHAR(50) NOT NULL,
                quantidade INT NOT NULL DEFAULT 0
            );
        """)

        # Tabela de Movimentações (Correção da coluna setor_destino)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS movimentacoes (
                id SERIAL PRIMARY KEY,
                empresa_cnpj VARCHAR(14) NOT NULL,
                tipo VARCHAR(100) NOT NULL,
                item_nome VARCHAR(255) NOT NULL,
                quantidade INT NOT NULL,
                paciente_nome VARCHAR(255),
                setor_destino VARCHAR(150),
                responsavel VARCHAR(255),
                data_movimentacao VARCHAR(50) NOT NULL
            );
        """)

        # Tabela de Tecnovigilância
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tecnovigilancia (
                id SERIAL PRIMARY KEY,
                empresa_cnpj VARCHAR(14) NOT NULL,
                lote_texto VARCHAR(255) NOT NULL,
                tipo_ocorrencia VARCHAR(150) NOT NULL,
                gravidade VARCHAR(100) NOT NULL,
                descricao TEXT NOT NULL,
                conduta TEXT NOT NULL,
                data_registro VARCHAR(50) NOT NULL
            );
        """)

        # Criar um operador padrão caso a tabela esteja vazia (Para testes iniciais)
        cursor.execute("SELECT COUNT(*) FROM colaboradores")
        if cursor.fetchone()['count'] == 0:
            cursor.execute("""
                INSERT INTO colaboradores (cpf, nome, cargo, empresa_cnpj) 
                VALUES ('12345678901', 'Farmacêutico Plantonista', 'Responsável Técnico', '00000000000000')
            """)

        conn.commit()
        cursor.close()
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro de infraestrutura do Banco: {str(e)}")

# =========================================================================
# MODELOS DE ENTRADA PYDANTIC (VALIDADORES)
# =========================================================================
class PharmacyLoginSchema(BaseModel):
    cpf: str

class AdminAuthSchema(BaseModel):
    cnpj: str
    senha: str

class DispensaPostSchema(BaseModel):
    empresa_cnpj: str
    tipo: str
    id_item: int
    paciente: str
    setor: str
    qtd: int
    responsavel: str

class MedPostSchema(BaseModel):
    empresa_cnpj: str
    codigo_barras: str
    nome: str
    principio_ativo: str
    categoria: str
    controlado: int

class LotePostSchema(BaseModel):
    medicamento_id: int
    numero_lote: str
    fabricante: str
    validade: str
    quantidade: int

class InsumoPostSchema(BaseModel):
    empresa_cnpj: str
    nome: str
    especificacao: str
    unidade_medida: str
    quantidade: int

class TecnoPostSchema(BaseModel):
    empresa_cnpj: str
    lote_texto: str
    tipo_ocorrencia: str
    gravidade: str
    descricao: str
    conduta: str

# =========================================================================
# ROTAS EXIGIDAS PELO FRONTEND DO DIA 16
# =========================================================================

@app.post("/api/pharmacy/login")
def pharmacy_login(dados: PharmacyLoginSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT cpf, nome, cargo, empresa_cnpj FROM colaboradores WHERE cpf = %s", (dados.cpf,))
    colaborador = cursor.fetchone()
    db.close()

    if colaborador:
        return {"success": True, "colaborador": colaborador}
    return {"success": False, "message": "Operador não cadastrado no sistema deste Hospital."}

@app.get("/api/pharmacy/sync")
def pharmacy_sync(cnpj: str):
    db = conectar_bd()
    cursor = db.cursor()
    
    # 1. Medicamentos
    cursor.execute("SELECT id, nome, principio_ativo, categoria, codigo_barras, controlado FROM medicamentos WHERE empresa_cnpj = %s", (cnpj,))
    meds = cursor.fetchall()
    
    # 2. Lotes ativos
    cursor.execute("""
        SELECT l.id, l.medicamento_id, l.numero_lote, l.fabricante, to_char(l.validade, 'YYYY-MM-DD') as validade, l.quantidade 
        FROM lotes l 
        JOIN medicamentos m ON l.medicamento_id = m.id 
        WHERE m.empresa_cnpj = %s
    """, (cnpj,))
    lotes = cursor.fetchall()
    
    # 3. Insumos
    cursor.execute("SELECT id, nome, especificacao, unidade_medida, quantidade FROM insumos WHERE empresa_cnpj = %s", (cnpj,))
    insumos = cursor.fetchall()
    
    # 4. Movimentações
    cursor.execute("SELECT tipo, item_nome, quantidade, paciente_nome, setor_destino, data_movimentacao, responsavel FROM movimentacoes WHERE empresa_cnpj = %s ORDER BY id DESC", (cnpj,))
    movs = cursor.fetchall()
    
    # 5. Tecnovigilância
    cursor.execute("SELECT lote_texto, tipo_ocorrencia, gravidade, data_registro FROM tecnovigilancia WHERE empresa_cnpj = %s ORDER BY id DESC", (cnpj,))
    tecno = cursor.fetchall()
    
    db.close()
    return {
        "success": True,
        "medicamentos": meds,
        "lotes": lotes,
        "insumos": insumos,
        "movimentacoes": movs,
        "tecnovigilancia": tecno
    }

@app.post("/api/pharmacy/dispensar")
def pharmacy_dispensar(disp: DispensaPostSchema):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        item_nome = ""
        if disp.tipo == "MED":
            cursor.execute("SELECT m.nome, l.quantidade FROM lotes l JOIN medicamentos m ON l.medicamento_id = m.id WHERE l.id = %s", (disp.id_item,))
            res = cursor.fetchone()
            if not res or res['quantidade'] < disp.qtd:
                raise HTTPException(status_code=400, detail="Saldo insuficiente.")
            item_nome = res['nome']
            cursor.execute("UPDATE lotes SET quantidade = quantidade - %s WHERE id = %s", (disp.qtd, disp.id_item))
        else:
            cursor.execute("SELECT nome, quantidade FROM insumos WHERE id = %s", (disp.id_item,))
            res = cursor.fetchone()
            if not res or res['quantidade'] < disp.qtd:
                raise HTTPException(status_code=400, detail="Saldo insuficiente.")
            item_nome = res['nome']
            cursor.execute("UPDATE insumos SET quantidade = quantidade - %s WHERE id = %s", (disp.qtd, disp.id_item))

        # Salva a movimentação usando exatamente as colunas e formatos de data esperados pelo front
        data_formatada = datetime.now().strftime("%d/%m/%Y, %H:%M")
        cursor.execute("""
            INSERT INTO movimentacoes (empresa_cnpj, tipo, item_nome, quantidade, paciente_nome, setor_destino, responsavel, data_movimentacao)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (disp.empresa_cnpj, f"SAÍDA {disp.tipo}", item_nome, disp.qtd, disp.paciente, disp.setor, disp.responsavel, data_formatada))
        
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}
    finally:
        db.close()

@app.post("/api/pharmacy/medicamentos")
def pharmacy_add_med(med: MedPostSchema):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO medicamentos (empresa_cnpj, codigo_barras, nome, principio_ativo, categoria, controlado)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (med.empresa_cnpj, med.codigo_barras, med.nome, med.principio_ativo, med.categoria, med.controlado))
        db.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        db.close()

@app.post("/api/pharmacy/lotes")
def pharmacy_add_lote(lote: LotePostSchema):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO lotes (medicamento_id, numero_lote, fabricante, validade, quantidade)
            VALUES (%s, %s, %s, %s, %s)
        """, (lote.medicamento_id, lote.numero_lote, lote.fabricante, lote.validade, lote.quantidade))
        db.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        db.close()

@app.post("/api/pharmacy/insumos")
def pharmacy_add_insumo(ins: InsumoPostSchema):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO insumos (empresa_cnpj, nome, especificacao, unidade_medida, quantidade)
            VALUES (%s, %s, %s, %s, %s)
        """, (ins.empresa_cnpj, ins.nome, ins.especificacao, ins.unidade_medida, ins.quantidade))
        db.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        db.close()

@app.post("/api/pharmacy/tecnovigilancia")
def pharmacy_add_tecno(tecno: TecnoPostSchema):
    db = conectar_bd()
    cursor = db.cursor()
    try:
        data_formatada = datetime.now().strftime("%d/%m/%Y %H:%M")
        cursor.execute("""
            INSERT INTO tecnovigilancia (empresa_cnpj, lote_texto, tipo_ocorrencia, gravidade, descricao, conduta, data_registro)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (tecno.empresa_cnpj, tecno.lote_texto, tecno.tipo_ocorrencia, tecno.gravidade, tecno.descricao, tecno.conduta, data_formatada))
        db.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        db.close()

# Rota para autenticação do Administrador no admin.html
@app.post("/api/admin/auth")
def admin_auth(dados: AdminAuthSchema):
    db = conectar_bd()
    cursor = db.cursor()
    cursor.execute("SELECT cnpj, hospital_nome FROM administradores WHERE cnpj=%s AND senha=%s", (dados.cnpj, dados.senha))
    admin = cursor.fetchone()
    db.close()
    if admin:
        return {"success": True, "admin": admin}
    return {"success": False, "message": "Credenciais administrativas inválidas."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
