import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date
import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field
from typing import Optional

app = FastAPI(
    title="YANA API - Central de Abastecimento Farmacêutico (PostgreSQL)",
    description="Backend em nuvem para controle interno e rastreabilidade hospitalar",
    version="1.1.1"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

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

        # 2. TABELA DE MEDICAMENTOS
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

        # 3. TABELA DE LOTES DE MEDICAMENTOS
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

        # 4. TABELA DE INSUMOS
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

        # 5. TABELA DE LOTES DE INSUMOS
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
                usuario_dono VARCHAR(150) NOT NULL DEFAULT 'admin'
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
                operador VARCHAR(255) NOT NULL,
                usuario_dono VARCHAR(150) NOT NULL DEFAULT 'admin'
            );
        """)

        conn.commit()
        cursor.close()
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro crítico de infraestrutura do Banco: {str(e)}")

# SCHEMAS DE VALIDAÇÃO
class LoginSchema(BaseModel):
    usuario: str
    senha: str

class MedicamentoSchema(BaseModel):
    nome: str
    principio_ativo: str
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
    quantidade: int
    usuario_dono: str

class InsumoSchema(BaseModel):
    nome: str
    especificacao: str
    unidade_medida: str
    grupo: str
    usuario_dono: str

class LoteInsumoSchema(BaseModel):
    insumo_id: int
    numero_lote: str
    fabricante: str
    validade: str
    quantidade: int
    usuario_dono: str

class DispensacaoSchema(BaseModel):
    tipo_material: str
    lote_id: int
    quantidade: int
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

class AtualizarUsuarioSchema(BaseModel):
    usuario: str
    senha: str
    perfil: str

# ENDPOINTS CORRIGIDOS E CONSOLIDADOS
@app.get("/api/dashboard/resumo", tags=["Auditoria Sanitária"])
def obter_resumo_dashboard_vencidos(usuario: str = "admin"):
    db = conectar_bd()
    try:
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
        
        alertas = []
        for r in lotes_med:
            alertas.append({"tipo": "MEDICAMENTO VENCIDO", "detalhe": f"{r['nome']} (Lote: {r['numero_lote']})", "validade": str(r['validade']), "estoque": r['quantidade']})
        for r in lotes_ins:
            alertas.append({"tipo": "INSUMO VENCIDO", "detalhe": f"{r['nome']} (Lote: {r['numero_lote']})", "validade": str(r['validade']), "estoque": r['quantidade']})
        return {"vencidos": alertas, "total_criticos": len(alertas)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.delete("/api/auth/usuarios/{usuario_id}", tags=["Autenticação"])
def deletar_usuario_unidade(usuario_id: int):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
        db.commit()
        return {"status": "sucesso", "mensagem": "Unidade revogada."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.put("/api/auth/usuarios/{usuario_id}", tags=["Autenticação"])
def atualizar_usuario_unidade(usuario_id: int, dados: AtualizarUsuarioSchema):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("""
            UPDATE usuarios SET usuario = %s, senha = %s, perfil = %s WHERE id = %s
        """, (dados.usuario, dados.senha, dados.perfil, usuario_id))
        db.commit()
        return {"status": "sucesso", "mensagem": "Dados atualizados com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/auth/verificar-admin", tags=["Autenticação"])
def verificar_senha_master_admin(dados: VerificarAdminSchema):
    senha_env = os.getenv("ADMIN_PASSWORD") or "Mudar@123_Seguro"
    if dados.senha.strip() == senha_env.strip():
        return {"status": "sucesso", "autorizado": True}
    raise HTTPException(status_code=401, detail="Senha Master incorreta.")

@app.post("/api/auth/registrar", tags=["Autenticação"])
def registrar_novo_usuario_unidade(dados: AtualizarUsuarioSchema):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO usuarios (usuario, senha, perfil) VALUES (%s, %s, %s)",
            (dados.usuario, dados.senha, dados.perfil)
        )
        db.commit()
        return {"status": "sucesso", "mensagem": "Unidade ativada com sucesso."}
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=400, detail="Esta unidade já encontra-se registrada.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/auth/usuarios", tags=["Autenticação"])
def listar_usuarios_unidades():
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id, usuario, perfil FROM usuarios ORDER BY id DESC")
        return cursor.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/auth/login", tags=["Autenticação"])
def login(dados: LoginSchema):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT usuario, perfil FROM usuarios WHERE usuario=%s AND senha=%s", (dados.usuario, dados.senha))
        user = cursor.fetchone()
        if user:
            return {"status": "sucesso", "usuario": user["usuario"], "perfil": user["perfil"]}
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/medicamentos", tags=["Medicamentos"])
def listar_medicamentos(usuario: str = "admin"):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id, nome, principio_ativo, categoria, codigo_barras, controlado FROM medicamentos WHERE usuario_dono = %s ORDER BY id DESC", (usuario,))
        resultado = cursor.fetchall()
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/medicamentos", tags=["Medicamentos"])
def cadastrar_medicamento(med: MedicamentoSchema):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO medicamentos (nome, principio_ativo, categoria, controlado, codigo_barras, usuario_dono) VALUES (%s,%s,%s,%s,%s,%s)",
            (med.nome, med.principio_ativo, med.categoria, med.controlado, med.codigo_barras, med.usuario_dono)
        )
        db.commit()
        return {"status": "sucesso", "mensagem": "Medicamento catalogado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/lotes/medicamentos", tags=["Lotes & Estoque"])
def listar_lotes_medicamentos(usuario: str = "admin"):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT l.id, med.nome as medicamento, l.numero_lote, l.fabricante, l.validade, l.quantidade 
            FROM lotes l JOIN medicamentos med ON l.medicamento_id = med.id
            WHERE l.quantidade > 0 AND l.usuario_dono = %s
        """, (usuario,))
        res = cursor.fetchall()
        # Converte as datas em string para o JSON do FastAPI não dar erro
        for r in res:
            if 'validade' in r and r['validade']:
                r['validade'] = str(r['validade'])
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/lotes/medicamentos", tags=["Lotes & Estoque"])
def receber_lote_medicamento(lote: LoteMedicamentoSchema):
    try:
        data_validade = datetime.strptime(lote.validade, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de validade inválido.")
    
    db = conectar_bd()
    try:
        cursor = db.cursor()
        fabricacao = lote.data_fabricacao if lote.data_fabricacao and lote.data_fabricacao.strip() != "" else None
        cursor.execute(
            "INSERT INTO lotes (medicamento_id, numero_lote, fabricante, data_fabricacao, validade, quantidade, usuario_dono) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (lote.medicamento_id, lote.numero_lote, lote.fabricante, fabricacao, data_validade, lote.quantidade, lote.usuario_dono)
        )
        db.commit()
        return {"status": "sucesso", "mensagem": "Lote incorporado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/insumos", tags=["Insumos"])
def listar_insumos(usuario: str = "admin"):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id, nome, especificacao, unidade_medida, grupo FROM insumos WHERE usuario_dono = %s ORDER BY id DESC", (usuario,))
        return cursor.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/insumos", tags=["Insumos"])
def cadastrar_insumo(ins: InsumoSchema):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO insumos (nome, especificacao, unidade_medida, grupo, usuario_dono) VALUES (%s, %s, %s, %s, %s)",
            (ins.nome, ins.especificacao, ins.unidade_medida, ins.grupo, ins.usuario_dono)
        )
        db.commit()
        return {"status": "sucesso", "mensagem": "Insumo catalogado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/lotes/insumos", tags=["Lotes & Estoque"])
def listar_lotes_insumos(usuario: str = "admin"):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT li.id, i.nome as insumo, li.numero_lote, li.fabricante, li.validade, li.quantidade 
            FROM lotes_insumos li JOIN insumos i ON li.insumo_id = i.id
            WHERE li.quantidade > 0 AND li.usuario_dono = %s
        """, (usuario,))
        res = cursor.fetchall()
        for r in res:
            if 'validade' in r and r['validade']:
                r['validade'] = str(r['validade'])
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/lotes/insumos", tags=["Lotes & Estoque"])
def receber_lote_insumo(lote: LoteInsumoSchema):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO lotes_insumos (insumo_id, numero_lote, fabricante, validade, quantidade, usuario_dono) VALUES (%s, %s, %s, %s, %s, %s)",
            (lote.insumo_id, lote.numero_lote, lote.fabricante, lote.validade, lote.quantidade, lote.usuario_dono)
        )
        db.commit()
        return {"status": "sucesso", "mensagem": "Lote de insumo incorporado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/dispensacao", tags=["Dispensação unificada"])
def processar_dispensacao(disp: DispensacaoSchema):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        if disp.tipo_material == "MEDICAMENTO":
            cursor.execute("SELECT quantidade FROM lotes WHERE id = %s AND usuario_dono = %s", (disp.lote_id, disp.usuario_dono))
            lote = cursor.fetchone()
            if not lote or lote["quantidade"] < disp.quantidade:
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
        return {"status": "sucesso", "mensagem": "Dispensação processada!"}
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Erro de transação: {str(e)}")
    finally:
        db.close()

@app.get("/api/auditoria/movimentacoes", tags=["Auditoria & Compliance"])
def relatorio_rastreabilidade(usuario: str = "admin"):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT id, lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao 
            FROM movimentacoes WHERE usuario_dono = %s ORDER BY id DESC
        """, (usuario,))
        return cursor.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/tecnovigilancia", tags=["Tecnovigilância (POP.FARM.019)"])
def registrar_ocorrencia(event: TecnovigilanciaSchema):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO tecnovigilancia (lote_texto, tipo_ocorrencia, descricao, gravidade, conduta, data_registro, operador, usuario_dono)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (event.lote_suspeito, event.tipo_ocorrencia, event.descricao, event.gravidade, event.conduta_imediata, datetime.now().strftime("%Y-%m-%d %H:%M"), event.operador, event.usuario_dono))
        db.commit()
        return {"status": "sucesso", "mensagem": "Ocorrência protocolada."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/tecnovigilancia", tags=["Tecnovigilância (POP.FARM.019)"])
def listar_ocorrencias_tecnovigilancia(usuario: str = "admin"):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT id, lote_texto AS lote_suspeito, tipo_ocorrencia, gravidade, data_registro, operador 
            FROM tecnovigilancia WHERE usuario_dono = %s ORDER BY id DESC
        """, (usuario,))
        return cursor.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
