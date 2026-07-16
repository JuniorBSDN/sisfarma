import os
import psycopg2
from psycopg2.extras import RealDictCursor
import random
import string
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# A Vercel injeta automaticamente a variável DATABASE_URL se integrar o Neon pelo painel,
# ou pode adicioná-la manualmente nas Environment Variables do projeto.
DATABASE_URL = os.environ.get("DATABASE_URL")


# =========================================================================
# LIGAÇÃO E INICIALIZAÇÃO DO POSTGRESQL (NEON)
# =========================================================================
def conectar_bd():
    # Cria a ligação utilizando a Connection String do Neon
    if not DATABASE_URL:
        raise ValueError("A variável de ambiente DATABASE_URL não está configurada.")
    return psycopg2.connect(DATABASE_URL)


def inicializar_banco():
    conn = conectar_bd()
    cursor = conn.cursor()

    # Tabela de Empresas (sisFarma Master) - PostgreSQL Syntax
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS empresas (
        id SERIAL PRIMARY KEY,
        razao_social TEXT NOT NULL,
        cnpj TEXT UNIQUE NOT NULL,
        email TEXT NOT NULL,
        telefone TEXT,
        plano TEXT NOT NULL,
        status TEXT DEFAULT 'Ativa',
        senha TEXT NOT NULL
    )
    ''')

    # Tabela de Funcionários/Colaboradores (sisFarma Admin Local)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS colaboradores (
        id SERIAL PRIMARY KEY,
        empresa_cnpj TEXT NOT NULL,
        nome TEXT NOT NULL,
        cpf TEXT UNIQUE NOT NULL,
        cargo TEXT NOT NULL,
        setor TEXT NOT NULL,
        status TEXT DEFAULT 'Ativa',
        FOREIGN KEY(empresa_cnpj) REFERENCES empresas(cnpj) ON DELETE CASCADE
    )
    ''')

    # Histórico de Acessos de Colaboradores (Logs de Auditoria)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs_acesso (
        id SERIAL PRIMARY KEY,
        colaborador_cpf TEXT NOT NULL,
        data_hora TEXT NOT NULL,
        ip TEXT NOT NULL,
        tipo TEXT NOT NULL,
        acao TEXT NOT NULL,
        FOREIGN KEY(colaborador_cpf) REFERENCES colaboradores(cpf) ON DELETE CASCADE
    )
    ''')

    # Tabelas de Operação da Farmácia Hospitalar (index.html)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS medicamentos (
        id SERIAL PRIMARY KEY,
        empresa_cnpj TEXT NOT NULL,
        nome TEXT NOT NULL,
        principio_ativo TEXT NOT NULL,
        categoria TEXT NOT NULL,
        controlado INTEGER DEFAULT 0,
        codigo_barras TEXT,
        FOREIGN KEY(empresa_cnpj) REFERENCES empresas(cnpj) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lotes (
        id SERIAL PRIMARY KEY,
        medicamento_id INTEGER NOT NULL,
        numero_lote TEXT NOT NULL,
        fabricante TEXT NOT NULL,
        validade TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        FOREIGN KEY(medicamento_id) REFERENCES medicamentos(id) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS insumos (
        id SERIAL PRIMARY KEY,
        empresa_cnpj TEXT NOT NULL,
        nome TEXT NOT NULL,
        especificacao TEXT NOT NULL,
        unidade_medida TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        FOREIGN KEY(empresa_cnpj) REFERENCES empresas(cnpj) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS movimentacoes (
        id SERIAL PRIMARY KEY,
        empresa_cnpj TEXT NOT NULL,
        tipo TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        setor_destino TEXT NOT NULL,
        paciente_nome TEXT NOT NULL,
        responsavel TEXT NOT NULL,
        data_movimentacao TEXT NOT NULL,
        FOREIGN KEY(empresa_cnpj) REFERENCES empresas(cnpj) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tecnovigilancia (
        id SERIAL PRIMARY KEY,
        empresa_cnpj TEXT NOT NULL,
        lote_texto TEXT NOT NULL,
        tipo_ocorrencia TEXT NOT NULL,
        gravidade TEXT NOT NULL,
        descricao TEXT NOT NULL,
        conduta TEXT NOT NULL,
        data_registro TEXT NOT NULL,
        FOREIGN KEY(empresa_cnpj) REFERENCES empresas(cnpj) ON DELETE CASCADE
    )
    ''')

    conn.commit()
    cursor.close()
    conn.close()


# Executa a inicialização de tabelas de forma segura caso a ligação exista
if DATABASE_URL:
    try:
        inicializar_banco()
        print("Tabelas do Banco de Dados Neon PostgreSQL prontas!")
    except Exception as e:
        print(f"Erro ao inicializar banco Neon: {e}")

# =========================================================================
# ROTAS OPERACIONAIS (SISFARMA - DISPENSAÇÃO E ESTOQUE)
# =========================================================================

def inicializar_tabelas_operacionais():
    conn = conectar_bd()
    cursor = conn.cursor()
    # Tabela de Catálogo de Medicamentos
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS medicamentos (
        id SERIAL PRIMARY KEY,
        codigo_barras TEXT UNIQUE,
        nome TEXT NOT NULL,
        principio TEXT,
        categoria TEXT,
        controlado BOOLEAN
    )''')
    # Tabela de Lotes
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lotes (
        id SERIAL PRIMARY KEY,
        med_id INTEGER REFERENCES medicamentos(id),
        numero TEXT NOT NULL,
        fabricante TEXT,
        validade DATE,
        quantidade INTEGER
    )''')
    # Tabela de Movimentações (Rastreabilidade)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS movimentacoes (
        id SERIAL PRIMARY KEY,
        tipo TEXT,
        item_nome TEXT,
        quantidade INTEGER,
        paciente TEXT,
        destino TEXT,
        data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    cursor.close()
    conn.close()

# Rota para sincronizar todos os dados do painel logado
@app.route('/api/pharmacy/sync', methods=['GET'])
def sync_pharmacy_data():
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM medicamentos")
    meds = cursor.fetchall()
    
    cursor.execute("SELECT * FROM lotes")
    lotes = cursor.fetchall()
    
    cursor.execute("SELECT * FROM movimentacoes ORDER BY data_hora DESC LIMIT 100")
    movs = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    # Formata datas para envio
    for l in lotes:
        if l.get('validade'):
            l['validade'] = l['validade'].strftime("%Y-%m-%d")
    for m in movs:
        if m.get('data_hora'):
            m['data_hora'] = m['data_hora'].strftime("%d/%m/%Y %H:%M:%S")

    return jsonify({"success": True, "medicamentos": meds, "lotes": lotes, "movimentacoes": movs})

# Rota para registrar uma dispensação (Baixa de Estoque)
@app.route('/api/pharmacy/dispensar', methods=['POST'])
def register_dispensa():
    data = request.json
    lote_id = data.get('lote_id')
    qtd_saida = int(data.get('qtd'))
    
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Verifica Saldo
    cursor.execute("SELECT quantidade, med_id FROM lotes WHERE id = %s", (lote_id,))
    lote = cursor.fetchone()
    
    if not lote or lote['quantidade'] < qtd_saida:
        return jsonify({"success": False, "message": "Estoque insuficiente!"})
        
    # Dá baixa no estoque
    cursor.execute("UPDATE lotes SET quantidade = quantidade - %s WHERE id = %s", (qtd_saida, lote_id))
    
    # Registra movimentação
    cursor.execute("SELECT nome FROM medicamentos WHERE id = %s", (lote['med_id'],))
    med = cursor.fetchone()
    
    cursor.execute('''
        INSERT INTO movimentacoes (tipo, item_nome, quantidade, paciente, destino)
        VALUES (%s, %s, %s, %s, %s)
    ''', ("SAÍDA MED", med['nome'], qtd_saida, data.get('paciente'), data.get('setor')))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({"success": True})

# =========================================================================
# FUNÇÕES AUXILIARES
# =========================================================================
def gerar_senha_aleatoria():
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
    return "sF_" + "".join(random.choice(chars) for _ in range(8))


def verificar_senha_master(senha):
    # Puxa a variável de ambiente configurada na Vercel
    senha_correta = os.environ.get("ADMIN_MASTER_PASSWORD")
    return senha == senha_correta


# =========================================================================
# ROTAS DO PAINEL MASTER (master.html)
# =========================================================================

@app.route('/api/master/auth', methods=['POST'])
def auth_master():
    data = request.json or {}
    senha = data.get("senha")
    if verificar_senha_master(senha):
        return jsonify({"success": True, "token": "master_session_granted"}), 200
    return jsonify({"success": False, "message": "Senha Master Incorreta."}), 401


@app.route('/api/master/companies', methods=['GET', 'POST'])
def manage_companies():
    conn = conectar_bd()
    # RealDictCursor faz com que o psycopg2 devolva os dados como dicionário chave:valor
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == 'POST':
        data = request.json or {}
        razao_social = data.get("razao_social")
        cnpj = data.get("cnpj")
        email = data.get("email")
        telefone = data.get("telefone")
        plano = data.get("plano")
        status = data.get("status", "Ativa")
        senha_gerada = gerar_senha_aleatoria()

        try:
            # Substituição de ? por %s necessária no PostgreSQL
            cursor.execute('''
                INSERT INTO empresas (razao_social, cnpj, email, telefone, plano, status, senha)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (razao_social, cnpj, email, telefone, plano, status, senha_gerada))
            conn.commit()
            return jsonify({"success": True, "cnpj": cnpj, "senha": senha_gerada}), 201
        except psycopg2.IntegrityError:
            conn.rollback()
            return jsonify({"success": False, "message": "Este CNPJ já está cadastrado no sistema."}), 400
        finally:
            cursor.close()
            conn.close()

    cursor.execute("SELECT * FROM empresas")
    companies = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(companies), 200


@app.route('/api/master/companies/<cnpj>/status', methods=['PUT'])
def toggle_company_status(cnpj):
    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("SELECT status FROM empresas WHERE cnpj = %s", (cnpj,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Empresa não localizada."}), 404

    novo_status = "Inativa" if row["status"] == "Ativa" else "Ativa"
    cursor.execute("UPDATE empresas SET status = %s WHERE cnpj = %s", (novo_status, cnpj))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "new_status": novo_status}), 200


# =========================================================================
# ROTAS DO PAINEL ADMIN LOCAL (admin.html)
# =========================================================================

@app.route('/api/admin/auth', methods=['POST'])
def auth_admin():
    data = request.json or {}
    cnpj = data.get("cnpj")
    senha = data.get("senha")

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM empresas WHERE cnpj = %s AND senha = %s", (cnpj, senha))
    company = cursor.fetchone()
    cursor.close()
    conn.close()

    if company:
        if company["status"] != "Ativa":
            return jsonify({"success": False, "message": "Licença suspensa. Contacte a equipa técnica Master."}), 403
        return jsonify({"success": True, "cnpj": cnpj, "razao_social": company["razao_social"]}), 200
    return jsonify({"success": False, "message": "Credenciais de licenciamento corporativo incorretas."}), 401


@app.route('/api/admin/employees', methods=['GET', 'POST'])
def manage_employees():
    cnpj_header = request.headers.get("X-Company-CNPJ")
    if not cnpj_header:
        return jsonify({"success": False, "message": "Cabeçalho de identificação (CNPJ da Farmácia) ausente."}), 400

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == 'POST':
        data = request.json or {}
        nome = data.get("nome")
        cpf = data.get("cpf")
        cargo = data.get("cargo")
        setor = data.get("setor")
        status = data.get("status", "Ativa")

        try:
            cursor.execute('''
                INSERT INTO colaboradores (empresa_cnpj, nome, cpf, cargo, setor, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (cnpj_header, nome, cpf, cargo, setor, status))
            conn.commit()
            return jsonify({"success": True, "cpf": cpf}), 201
        except psycopg2.IntegrityError:
            conn.rollback()
            return jsonify(
                {"success": False, "message": "Este CPF já se encontra cadastrado nesta ou noutra unidade."}), 400
        finally:
            cursor.close()
            conn.close()

    cursor.execute("SELECT * FROM colaboradores WHERE empresa_cnpj = %s", (cnpj_header,))
    employees = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(employees), 200


# =========================================================================
# ROTAS DA OPERAÇÃO DE FARMÁCIA (index.html)
# =========================================================================

@app.route('/api/pharmacy/login', methods=['POST'])
def employee_login():
    data = request.json or {}
    cpf = data.get("cpf")
    ip_cliente = request.remote_addr or "127.0.0.1"

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM colaboradores WHERE cpf = %s", (cpf,))
    colab = cursor.fetchone()

    if not colab:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Colaborador ou crachá não localizado no sistema."}), 401

    if colab["status"] != "Ativa":
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Acesso Suspenso. Por favor, consulte a Administração."}), 403

    # Registra Log de Login
    cursor.execute('''
        INSERT INTO logs_acesso (colaborador_cpf, data_hora, ip, tipo, acao)
        VALUES (%s, %s, %s, %s, %s)
    ''', (cpf, datetime.now().strftime("%Y-%m-%d %H:%M"), ip_cliente, "QR Code", "Login efetuado com sucesso"))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({
        "success": True,
        "colaborador": {
            "nome": colab["nome"],
            "cargo": colab["cargo"],
            "setor": colab["setor"],
            "empresa_cnpj": colab["empresa_cnpj"]
        }
    }), 200


@app.route('/')
def home():
    return jsonify({"status": "sisFarma API on Neon PostgreSQL is online", "version": "1.0.0"}), 200
