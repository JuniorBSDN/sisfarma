import os
import psycopg2
from psycopg2.extras import RealDictCursor
import random
import string
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# A Vercel injeta automaticamente a variável DATABASE_URL se integrar o Neon pelo painel
DATABASE_URL = os.environ.get("DATABASE_URL")


# =========================================================================
# LIGAÇÃO E INICIALIZAÇÃO DO POSTGRESQL (NEON)
# =========================================================================
def conectar_bd():
    if not DATABASE_URL:
        raise ValueError("A variável de ambiente DATABASE_URL não está configurada.")
    return psycopg2.connect(DATABASE_URL)


def inicializar_banco():
    conn = conectar_bd()
    cursor = conn.cursor()

    # Tabela de Empresas (sisFarma Master)
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

    # Tabelas de Operação da Farmácia Hospitalar (Consolidada)
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
        item_nome TEXT NOT NULL,
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
# FUNÇÕES AUXILIARES
# =========================================================================
def gerar_senha_aleatoria():
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
    return "sF_" + "".join(random.choice(chars) for _ in range(8))


def verificar_senha_master(senha):
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
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == 'POST':
        data = request.json or {}
        razao_social = data.get("razao_social")
        cnpj = data.get("cnpj")
        email = data.get("email")
        telefone = data.get("telefone")
        plano = data.get("plano")
        status = data.get("status", "Ativo")
        senha_gerada = gerar_senha_aleatoria()

        try:
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
            return jsonify({"success": False, "message": "Este CPF já se encontra cadastrado nesta ou noutra unidade."}), 400
        finally:
            cursor.close()
            conn.close()

    cursor.execute("SELECT * FROM colaboradores WHERE empresa_cnpj = %s", (cnpj_header,))
    employees = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(employees), 200


# =========================================================================
# ROTAS DA OPERAÇÃO DE FARMÁCIA (index.html) - SEGURA POR CNPJ
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

   # Flexibilizamos para aceitar Ativo ou Ativa
    if colab["status"] not in ["Ativa", "Ativo", "ATIVO", "ATIVA"]:
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


# Sincroniza Medicamentos, Lotes, Insumos, Saídas e Tecnovigilância filtrados pelo CNPJ da Unidade Hospitalar
@app.route('/api/pharmacy/sync', methods=['GET'])
def sync_pharmacy_data():
    cnpj = request.args.get("cnpj")
    if not cnpj:
        return jsonify({"success": False, "message": "Parâmetro CNPJ ausente."}), 400

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Puxa medicamentos da empresa logada
    cursor.execute("SELECT * FROM medicamentos WHERE empresa_cnpj = %s", (cnpj,))
    meds = cursor.fetchall()

    # 2. Puxa lotes cujos medicamentos pertençam a essa empresa
    cursor.execute('''
        SELECT l.*, m.nome as med_nome FROM lotes l
        JOIN medicamentos m ON l.medicamento_id = m.id
        WHERE m.empresa_cnpj = %s
    ''', (cnpj,))
    lotes = cursor.fetchall()

    # 3. Puxa Insumos da empresa
    cursor.execute("SELECT * FROM insumos WHERE empresa_cnpj = %s", (cnpj,))
    insumos = cursor.fetchall()

    # 4. Puxa Rastreabilidade / Movimentações
    cursor.execute("SELECT * FROM movimentacoes WHERE empresa_cnpj = %s ORDER BY id DESC LIMIT 100", (cnpj,))
    movs = cursor.fetchall()

    # 5. Puxa Registros de Tecnovigilância
    cursor.execute("SELECT * FROM tecnovigilancia WHERE empresa_cnpj = %s ORDER BY id DESC", (cnpj,))
    tecno = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify({
        "success": True,
        "medicamentos": meds,
        "lotes": lotes,
        "insumos": insumos,
        "movimentacoes": movs,
        "tecnovigilancia": tecno
    })


# Registrar novo Medicamento no Catálogo Base da empresa
@app.route('/api/pharmacy/medicamentos', methods=['POST'])
def add_medicamento():
    data = request.json or {}
    cnpj = data.get("empresa_cnpj")
    nome = data.get("nome")
    principio = data.get("principio_ativo")
    categoria = data.get("categoria")
    controlado = int(data.get("controlado", 0))
    codigo_barras = data.get("codigo_barras")

    if not cnpj:
        return jsonify({"success": False, "message": "CNPJ não informado."}), 400

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute('''
            INSERT INTO medicamentos (empresa_cnpj, nome, principio_ativo, categoria, controlado, codigo_barras)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        ''', (cnpj, nome, principio, categoria, controlado, codigo_barras))
        new_id = cursor.fetchone()['id']
        conn.commit()
        return jsonify({"success": True, "id": new_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# Registrar Entrada de Lote vinculado a um Medicamento do Catálogo
@app.route('/api/pharmacy/lotes', methods=['POST'])
def add_lote():
    data = request.json or {}
    med_id = data.get("medicamento_id")
    numero = data.get("numero_lote")
    fabricante = data.get("fabricante")
    validade = data.get("validade")
    quantidade = int(data.get("quantidade", 0))

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute('''
            INSERT INTO lotes (medicamento_id, numero_lote, fabricante, validade, quantidade)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        ''', (med_id, numero, fabricante, validade, quantidade))
        new_id = cursor.fetchone()['id']
        conn.commit()
        return jsonify({"success": True, "id": new_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# Registrar Entrada de Insumo Correlato
@app.route('/api/pharmacy/insumos', methods=['POST'])
def add_insumo():
    data = request.json or {}
    cnpj = data.get("empresa_cnpj")
    nome = data.get("nome")
    especificacao = data.get("especificacao")
    unidade = data.get("unidade_medida")
    quantidade = int(data.get("quantidade", 0))

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute('''
            INSERT INTO insumos (empresa_cnpj, nome, especificacao, unidade_medida, quantidade)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        ''', (cnpj, nome, especificacao, unidade, quantidade))
        new_id = cursor.fetchone()['id']
        conn.commit()
        return jsonify({"success": True, "id": new_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# Registrar Baixa/Dispensação por Lote ou Insumo
@app.route('/api/pharmacy/dispensar', methods=['POST'])
def register_dispensa():
    data = request.json or {}
    cnpj = data.get("empresa_cnpj")
    tipo = data.get("tipo")  # "MED" ou "INS"
    id_item = data.get("id_item")  # lote_id se MED, insumo_id se INS
    qtd_saida = int(data.get("qtd", 0))
    paciente = data.get("paciente")
    setor = data.get("setor")
    responsavel = data.get("responsavel", "Operador Geral")

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        if tipo == "MED":
            # Puxa o lote
            cursor.execute("SELECT quantidade, medicamento_id FROM lotes WHERE id = %s", (id_item,))
            lote = cursor.fetchone()
            if not lote or lote['quantidade'] < qtd_saida:
                return jsonify({"success": False, "message": "Estoque de lote insuficiente!"}), 400

            # Atualiza o saldo do Lote
            cursor.execute("UPDATE lotes SET quantidade = quantidade - %s WHERE id = %s", (qtd_saida, id_item))

            # Captura nome do medicamento
            cursor.execute("SELECT nome FROM medicamentos WHERE id = %s", (lote['medicamento_id'],))
            med = cursor.fetchone()
            item_nome = med['nome']
        else:
            # Puxa o Insumo
            cursor.execute("SELECT quantidade, nome FROM insumos WHERE id = %s", (id_item,))
            ins = cursor.fetchone()
            if not ins or ins['quantidade'] < qtd_saida:
                return jsonify({"success": False, "message": "Estoque de insumos insuficiente!"}), 400

            # Atualiza o saldo do Insumo
            cursor.execute("UPDATE insumos SET quantidade = quantidade - %s WHERE id = %s", (qtd_saida, id_item))
            item_nome = ins['nome']

        # Grava na tabela de Movimentações
        data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        cursor.execute('''
            INSERT INTO movimentacoes (empresa_cnpj, tipo, item_nome, quantidade, setor_destino, paciente_nome, responsavel, data_movimentacao)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (cnpj, f"SAÍDA {tipo}", item_nome, qtd_saida, setor, paciente, responsavel, data_atual))

        conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# Registrar Ocorrência de Tecnovigilância
@app.route('/api/pharmacy/tecnovigilancia', methods=['POST'])
def add_tecnovigilancia():
    data = request.json or {}
    cnpj = data.get("empresa_cnpj")
    lote_texto = data.get("lote_texto")
    tipo_ocorrencia = data.get("tipo_ocorrencia")
    gravidade = data.get("gravidade")
    descricao = data.get("descricao")
    conduta = data.get("conduta")
    data_registro = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    conn = conectar_bd()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute('''
            INSERT INTO tecnovigilancia (empresa_cnpj, lote_texto, tipo_ocorrencia, gravidade, descricao, conduta, data_registro)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (cnpj, lote_texto, tipo_ocorrencia, gravidade, descricao, conduta, data_registro))
        conn.commit()
        return jsonify({"success": True}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/')
def home():
    return jsonify({"status": "sisFarma API on Neon PostgreSQL is online", "version": "1.0.0"}), 200
