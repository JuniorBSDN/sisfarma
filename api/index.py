import os
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date

import psycopg2
from psycopg2.extras import RealDictCursor  # Mantém o acesso às colunas por nome
from pydantic import BaseModel, Field
from datetime import datetime
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


# 🛠️ GERENCIADOR DE CONEXÃO E ESTRUTURA DO BANCO DE DADOS
def conectar_bd():
    try:
        # Abre a conexão segura com o banco PostgreSQL
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
                data_fabricacao DATE,
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
    controlado: int  # 0 ou 1 conforme o dicionário
    codigo_barras: str


class LoteMedicamentoSchema(BaseModel):
    medicamento_id: int
    numero_lote: str
    fabricante: str
    data_fabricacao: Optional[str] = None  # Tolerante se o frontend omitir
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
    data_fabricacao: Optional[str] = None
    validade: str
    quantidade: int = Field(..., gt=0)


class DispensacaoSchema(BaseModel):
    tipo_material: str  # "MEDICAMENTO" ou "INSUMO"
    lote_id: int
    quantidade
