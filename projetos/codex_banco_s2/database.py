import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, cpf TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL, categoria TEXT NOT NULL, situacao TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contas (
    id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    numero TEXT NOT NULL UNIQUE, tipo TEXT NOT NULL, saldo INTEGER NOT NULL DEFAULT 0,
    limite_credito INTEGER NOT NULL, estado TEXT NOT NULL, negativa_desde TEXT,
    criada_em TEXT NOT NULL, CHECK (saldo >= -limite_credito)
);
CREATE TABLE IF NOT EXISTS transacoes (
    id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas(id),
    destino_id INTEGER REFERENCES contas(id), tipo TEXT NOT NULL,
    valor INTEGER NOT NULL, data TEXT NOT NULL, estado TEXT NOT NULL,
    original_id INTEGER UNIQUE REFERENCES transacoes(id),
    usa_franquia INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cartoes (
    id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas(id),
    numero TEXT NOT NULL UNIQUE, limite INTEGER NOT NULL, estado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS faturas (
    id INTEGER PRIMARY KEY, cartao_id INTEGER NOT NULL REFERENCES cartoes(id),
    mes_referencia TEXT NOT NULL, vencimento TEXT NOT NULL, valor_base INTEGER NOT NULL,
    valor INTEGER NOT NULL, estado TEXT NOT NULL, paga_em TEXT,
    UNIQUE (cartao_id, mes_referencia)
);
CREATE TABLE IF NOT EXISTS tarifas (
    id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas(id),
    transacao_id INTEGER UNIQUE REFERENCES transacoes(id), tipo TEXT NOT NULL,
    competencia TEXT NOT NULL, categoria TEXT NOT NULL, valor INTEGER NOT NULL,
    estado TEXT NOT NULL, cobrada_em TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS mensal_por_conta
    ON tarifas(conta_id, competencia) WHERE tipo = 'mensal';
CREATE INDEX IF NOT EXISTS transacoes_conta_data ON transacoes(conta_id, data);
CREATE INDEX IF NOT EXISTS transacoes_destino_data ON transacoes(destino_id, data);
CREATE INDEX IF NOT EXISTS contas_cliente ON contas(cliente_id);
CREATE INDEX IF NOT EXISTS cartoes_conta ON cartoes(conta_id);
"""


def conectar():
    padrao = Path(__file__).with_name("banco.sqlite3")
    db = sqlite3.connect(os.getenv("BANCO_DB", str(padrao)), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def inicializar():
    db = conectar()
    try:
        db.executescript(SCHEMA)
    finally:
        db.close()


@contextmanager
def unidade():
    db = conectar()
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            yield db
    finally:
        db.close()
