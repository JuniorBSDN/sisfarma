import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash

app = Flask(__name__)

# --- CONFIGURAÇÕES DE AMBIENTE (VERCEL) ---
# Usa exatamente os nomes das variáveis que você configurou no painel da Vercel
DATABASE_URL = os.environ.get('DATABASE_URL')
MASTER_PASSWORD = os.environ.get('ADMIN_MASTER_PASSWORD', 'admin123')

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# --- 1. ROTA DE SEGURANÇA (PROMPT) ---
@app.route('/api/auth/verificar-admin', methods=['POST'])
def verificar_admin():
    data = request.json
    if not data or data.get('senha') != MASTER_PASSWORD:
        return jsonify({"error": "Senha Master Inválida"}), 401
    
    return jsonify({"status": "sucesso"}), 200

# --- 2. LISTAR TODOS OS CLIENTES (GET) ---
@app.route('/api/auth/usuarios', methods=['GET'])
def listar_clientes():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca os dados da empresa e o usuário vinculado
        cur.execute("""
            SELECT t.id, t.nome_fantasia AS nome, t.cnpj, t.responsavel, t.telefone, 
                   t.email, t.cnae, t.tipo_contrato AS contrato, t.periodo, t.status_assinatura AS status,
                   u.usuario 
            FROM tenants t
            LEFT JOIN users u ON t.id = u.tenant_id
            ORDER BY t.id DESC;
        """)
        registros = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify(registros), 200
    except Exception as e:
        return jsonify({"error": "Erro ao acessar o banco de dados", "detail": str(e)}), 500

# --- 3. CADASTRAR NOVO CLIENTE (POST) ---
@app.route('/api/auth/registrar', methods=['POST'])
def registrar_cliente():
    data = request.json
    senha_hash = generate_password_hash(data['senha']) # Criptografa a senha do cliente
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Insere a Empresa
        cur.execute("""
            INSERT INTO tenants (nome_fantasia, cnpj, responsavel, telefone, email, cnae, tipo_contrato, periodo, status_assinatura) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """, (data['nome'], data['cnpj'], data['responsavel'], data['telefone'], data['email'], 
              data['cnae'], data['contrato'], data['periodo'], data['status']))
        
        tenant_id = cur.fetchone()['id']
        
        # Insere o Usuário Master daquela empresa
        cur.execute("""
            INSERT INTO users (tenant_id, usuario, senha_hash) VALUES (%s, %s, %s);
        """, (tenant_id, data['usuario'], senha_hash))
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "sucesso", "tenant_id": tenant_id}), 201
    except Exception as e:
        return jsonify({"error": "Falha ao cadastrar. Verifique se o Login ou CNPJ já existem.", "detail": str(e)}), 400

# --- 4. ATUALIZAR CLIENTE (PUT) ---
@app.route('/api/auth/usuarios/<int:id>', methods=['PUT'])
def atualizar_cliente(id):
    data = request.json
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Atualiza os dados da Empresa
        cur.execute("""
            UPDATE tenants 
            SET nome_fantasia=%s, cnpj=%s, responsavel=%s, telefone=%s, email=%s, 
                cnae=%s, tipo_contrato=%s, periodo=%s, status_assinatura=%s
            WHERE id = %s;
        """, (data['nome'], data['cnpj'], data['responsavel'], data['telefone'], data['email'], 
              data['cnae'], data['contrato'], data['periodo'], data['status'], id))
        
        # Atualiza o Usuário
        cur.execute("UPDATE users SET usuario=%s WHERE tenant_id=%s;", (data['usuario'], id))
        
        # Se a senha foi enviada no form, atualiza o Hash
        if 'senha' in data and data['senha'] != "":
            senha_hash = generate_password_hash(data['senha'])
            cur.execute("UPDATE users SET senha_hash=%s WHERE tenant_id=%s;", (senha_hash, id))
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "atualizado"}), 200
    except Exception as e:
        return jsonify({"error": "Erro ao atualizar dados", "detail": str(e)}), 400

# --- 5. EXCLUIR CLIENTE (DELETE) ---
@app.route('/api/auth/usuarios/<int:id>', methods=['DELETE'])
def deletar_cliente(id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Ao deletar o Tenant, o ON DELETE CASCADE do banco apagará o usuário associado
        cur.execute("DELETE FROM tenants WHERE id = %s;", (id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "apagado"}), 200
    except Exception as e:
        return jsonify({"error": "Erro ao apagar registro", "detail": str(e)}), 400

# Para rodar localmente, se necessário
if __name__ == '__main__':
    app.run(debug=True, port=5000)
