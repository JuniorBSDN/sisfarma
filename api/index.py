import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash

app = Flask(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://seu_usuario:sua_senha@neon.tech/dbname')
MASTER_PASSWORD = os.environ.get('ADMIN_SECRET', 'admin123')

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

@app.route('/api/auth/verificar-admin', methods=['POST'])
def verificar_admin():
    senha_digitada = request.json.get('senha')
    if senha_digitada == MASTER_PASSWORD:
        return jsonify({"status": "sucesso"}), 200
    return jsonify({"error": "Senha Inválida"}), 401

@app.route('/api/auth/usuarios', methods=['GET'])
def listar_clientes():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT t.id, t.nome_fantasia AS nome, t.cnpj, t.responsavel, t.telefone, 
                   t.email, t.cnae, t.tipo_contrato AS contrato, t.periodo, t.status_assinatura AS status,
                   u.usuario 
            FROM tenants t
            LEFT JOIN users u ON t.id = u.tenant_id
            ORDER BY t.id DESC;
        """)
        return jsonify(cur.fetchall()), 200
    finally:
        cur.close()
        conn.close()

@app.route('/api/auth/registrar', methods=['POST'])
def registrar_cliente():
    data = request.json
    senha_hash = generate_password_hash(data['senha'])
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Salva a Empresa
        cur.execute("""
            INSERT INTO tenants (nome_fantasia, cnpj, responsavel, telefone, email, cnae, tipo_contrato, periodo, status_assinatura) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """, (data['nome'], data['cnpj'], data['responsavel'], data['telefone'], data['email'], data['cnae'], data['contrato'], data['periodo'], data['status']))
        tenant_id = cur.fetchone()['id']
        
        # 2. Salva o Login vinculado à Empresa
        cur.execute("""
            INSERT INTO users (tenant_id, usuario, senha_hash) VALUES (%s, %s, %s);
        """, (tenant_id, data['usuario'], senha_hash))
        
        conn.commit()
        return jsonify({"status": "sucesso"}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

@app.route('/api/auth/usuarios/<int:id>', methods=['DELETE'])
def deletar_cliente(id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # ON DELETE CASCADE no banco apagará o usuário automaticamente
        cur.execute("DELETE FROM tenants WHERE id = %s;", (id,))
        conn.commit()
        return jsonify({"status": "apagado"}), 200
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=True)
