import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date
import psycopg2
from pydantic import BaseModel
from typing import Optional

app = FastAPI(
    title="YANA API - Central de Abastecimento Farmacêutico (PostgreSQL)",
    description="Backend em nuvem para controle interno e rastreabilidade hospitalar",
    version="1.1.3"
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
        # Usamos o cursor clássico para retornar tuplas compatíveis com o seu index.html (med[0], med[1]...)
        conn = psycopg2.connect(DATABASE_URL)
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
        raise HTTPException(status_code=500, detail=f"Erro de Banco: {str(e)}")

# SCHEMAS DE ENTRADA EXATOS
class LoginSchema(BaseModel):
    usuario: str
    senha: str

class MedicamentoSchema(BaseModel):
    nome: str
    principio_ativo: str
    categoria: str
    controlado: int
    codigo_barras: str
    usuario_dono: Optional[str] = "admin"

class LoteMedicamentoSchema(BaseModel):
    medicamento_id: int
    numero_lote: str
    fabricante: str
    data_fabricacao: Optional[str] = None
    validade: str
    quantidade: int
    usuario_dono: Optional[str] = "admin"

class InsumoSchema(BaseModel):
    nome: str
    especificacao: str
    unidade_medida: str
    grupo: str
    usuario_dono: Optional[str] = "admin"

class LoteInsumoSchema(BaseModel):
    insumo_id: int
    numero_lote: str
    fabricante: str
    validade: str
    quantidade: int
    usuario_dono: Optional[str] = "admin"

class DispensacaoSchema(BaseModel):
    tipo_material: str
    lote_id: int
    quantidade: int
    setor_destino: str
    paciente_nome: str
    prescricao_num: str
    responsavel: str
    usuario_dono: Optional[str] = "admin"

class TecnovigilanciaSchema(BaseModel):
    lote_suspeito: str
    tipo_ocorrencia: str
    descricao: str
    gravidade: str
    conduta_imediata: str
    operador: str
    usuario_dono: Optional[str] = "admin"

class VerificarAdminSchema(BaseModel):
    senha: str

class AtualizarUsuarioSchema(BaseModel):
    usuario: str
    senha: str
    perfil: str

# --- ENDPOINTS CONFIGURADOS ---

@app.post("/api/auth/login")
def login(dados: LoginSchema):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT usuario, perfil FROM usuarios WHERE usuario=%s AND senha=%s", (dados.usuario, dados.senha))
        user = cursor.fetchone()
        if user:
            return {"status": "sucesso", "usuario": user[0], "perfil": user[1]}
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")
    finally:
        db.close()

@app.get("/api/medicamentos")
def listar_medicamentos(usuario: str = "admin"):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id, nome, principio_ativo, categoria, codigo_barras, controlado FROM medicamentos WHERE usuario_dono = %s ORDER BY id DESC", (usuario,))
        return cursor.fetchall()
    finally:
        db.close()

@app.post("/api/medicamentos")
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
    finally:
        db.close()

@app.get("/api/lotes/medicamentos")
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
        # Formata datas para string evitando erros de JSON
        resultado_formatado = []
        for r in res:
            item = list(r)
            item[4] = str(item[4])
            resultado_formatado.append(item)
        return resultado_formatado
    finally:
        db.close()

@app.post("/api/lotes/medicamentos")
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
    finally:
        db.close()

@app.get("/api/insumos")
def listar_insumos(usuario: str = "admin"):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id, nome, especificacao, unidade_medida, grupo FROM insumos WHERE usuario_dono = %s ORDER BY id DESC", (usuario,))
        return cursor.fetchall()
    finally:
        db.close()

@app.post("/api/insumos")
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
    finally:
        db.close()

@app.get("/api/lotes/insumos")
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
        resultado_formatado = []
        for r in res:
            item = list(r)
            item[4] = str(item[4])
            resultado_formatado.append(item)
        return resultado_formatado
    finally:
        db.close()

@app.post("/api/lotes/insumos")
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
    finally:
        db.close()

@app.post("/api/dispensacao")
def processar_dispensacao(disp: DispensacaoSchema):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        if disp.tipo_material == "MEDICAMENTO":
            cursor.execute("SELECT quantidade FROM lotes WHERE id = %s AND usuario_dono = %s", (disp.lote_id, disp.usuario_dono))
            lote = cursor.fetchone()
            if not lote or lote[0] < disp.quantidade:
                raise HTTPException(status_code=400, detail="Saldo insuficiente no lote.")

            cursor.execute("UPDATE lotes SET quantidade = quantidade - %s WHERE id = %s AND usuario_dono = %s", (disp.quantidade, disp.lote_id, disp.usuario_dono))
            cursor.execute("""
                INSERT INTO movimentacoes (lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao, usuario_dono)
                VALUES (%s, NULL, 'SAÍDA MEDICAMENTO', %s, %s, %s, %s, %s, %s, %s)
            """, (disp.lote_id, disp.quantidade, disp.setor_destino, disp.paciente_nome, disp.prescricao_num, disp.responsavel, datetime.now().strftime("%Y-%m-%d %H:%M"), disp.usuario_dono))

        elif disp.tipo_material == "INSUMO":
            cursor.execute("SELECT quantidade FROM lotes_insumos WHERE id = %s AND usuario_dono = %s", (disp.lote_id, disp.usuario_dono))
            lote = cursor.fetchone()
            if not lote or lote[0] < disp.quantidade:
                raise HTTPException(status_code=400, detail="Saldo insuficiente.")

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
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/api/auditoria/movimentacoes")
def relatorio_rastreabilidade(usuario: str = "admin"):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT id, lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao 
            FROM movimentacoes WHERE usuario_dono = %s ORDER BY id DESC
        """, (usuario,))
        return cursor.fetchall()
    finally:
        db.close()

@app.post("/api/tecnovigilancia")
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
    finally:
        db.close()

@app.get("/api/tecnovigilancia")
def listar_ocorrencias_tecnovigilancia(usuario: str = "admin"):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT id, lote_texto, tipo_ocorrencia, gravidade, data_registro, operador 
            FROM tecnovigilancia WHERE usuario_dono = %s ORDER BY id DESC
        """, (usuario,))
        res = cursor.fetchall()
        # Mapeia como chaves que o HTML precisa no forEach (o.id, o.lote_suspeito...)
        resultado_objetos = []
        for r in res:
            resultado_objetos.append({
                "id": r[0],
                "lote_suspeito": r[1],
                "tipo_ocorrencia": r[2],
                "gravidade": r[3],
                "data_registro": r[4],
                "operador": r[5]
            })
        return resultado_objetos
    finally:
        db.close()

@app.get("/api/dashboard/resumo")
def obter_resumo_dashboard_vencidos(usuario: str = "admin"):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        data_atual = date.today()
        cursor.execute("""
            SELECT med.nome, l.numero_lote, l.validade, l.quantidade 
            FROM lotes l JOIN medicamentos med ON l.medicamento_id = med.id 
            WHERE l.quantidade > 0 AND l.validade <= %s AND l.usuario_dono = %s
        """, (data_atual, usuario))
        lotes_med = cursor.fetchall()

        cursor.execute("""
            SELECT i.nome, li.numero_lote, li.validade, li.quantidade 
            FROM lotes_insumos li JOIN insumos i ON li.insumo_id = i.id 
            WHERE li.quantidade > 0 AND li.validade <= %s AND li.usuario_dono = %s
        """, (data_atual, usuario))
        lotes_ins = cursor.fetchall()
        
        alertas = []
        for r in lotes_med:
            alertas.append({"tipo": "MEDICAMENTO VENCIDO", "detalhe": f"{r[0]} (Lote: {r[1]})", "validade": str(r[2]), "estoque": r[3]})
        for r in lotes_ins:
            alertas.append({"tipo": "INSUMO VENCIDO", "detalhe": f"{r[0]} (Lote: {r[1]})", "validade": str(r[2]), "estoque": r[3]})
        return {"vencidos": alertas, "total_criticos": len(alertas)}
    finally:
        db.close()

# --- ENDPOINTS EXCLUSIVOS DO ADMIN.HTML ---
@app.get("/api/auth/usuarios")
def listar_usuarios_unidades():
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id, usuario, perfil FROM usuarios ORDER BY id DESC")
        res = cursor.fetchall()
        resultado_objetos = []
        for r in res:
            resultado_objetos.append({"id": r[0], "usuario": r[1], "perfil": r[2]})
        return resultado_objetos
    finally:
        db.close()

@app.post("/api/auth/registrar")
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
    finally:
        db.close()

@app.put("/api/auth/usuarios/{usuario_id}")
def atualizar_usuario_unidade(usuario_id: int, dados: AtualizarUsuarioSchema):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("""
            UPDATE usuarios SET usuario = %s, senha = %s, perfil = %s WHERE id = %s
        """, (dados.usuario, dados.senha, dados.perfil, usuario_id))
        db.commit()
        return {"status": "sucesso", "mensagem": "Dados atualizados com sucesso."}
    finally:
        db.close()

@app.delete("/api/auth/usuarios/{usuario_id}")
def deletar_usuario_unidade(usuario_id: int):
    db = conectar_bd()
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
        db.commit()
        return {"status": "sucesso", "mensagem": "Unidade revogada."}
    finally:
        db.close()

@app.post("/api/auth/verificar-admin")
def verificar_senha_master_admin(dados: VerificarAdminSchema):
    senha_env = os.getenv("ADMIN_PASSWORD") or "Mudar@123_Seguro"
    if dados.senha.strip() == senha_env.strip():
        return {"status": "sucesso", "autorizado": True}
    raise HTTPException(status_code=401, detail="Senha Master incorreta.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
