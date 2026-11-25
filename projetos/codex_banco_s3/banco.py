import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

BANK_TZ = timezone(timedelta(hours=-3))
DB_PATH = os.environ.get("BANCO_DB", str(Path(__file__).with_name("banco.sqlite3")))
TRANSFER_FEE = Decimal(os.environ.get("BANCO_TARIFA_TRANSFERENCIA", "2.50"))
if not TRANSFER_FEE.is_finite() or not 0 < TRANSFER_FEE <= 10**12 or TRANSFER_FEE * 100 != int(TRANSFER_FEE * 100):
    raise ValueError("BANCO_TARIFA_TRANSFERENCIA deve ser um valor positivo em centavos.")

# Valores monetarios em centavos, juros em pontos percentuais.
RULES = {
    "comum": (100_000, 500_000, 3_000, 3, 8),
    "premium": (500_000, 5_000_000, 0, None, 5),
    "empresarial": (2_000_000, 20_000_000, 12_000, 50, 3),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
 id INTEGER PRIMARY KEY, nome TEXT NOT NULL, cpf TEXT NOT NULL UNIQUE,
 email TEXT NOT NULL, categoria TEXT NOT NULL, situacao TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contas (
 id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id),
 numero TEXT NOT NULL UNIQUE, tipo TEXT NOT NULL, saldo INTEGER NOT NULL DEFAULT 0,
 limite_credito INTEGER NOT NULL, estado TEXT NOT NULL DEFAULT 'ativa',
 negativa_desde TEXT, criada_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cartoes (
 id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas(id),
 numero TEXT NOT NULL UNIQUE, limite INTEGER NOT NULL, estado TEXT NOT NULL DEFAULT 'ativo'
);
CREATE TABLE IF NOT EXISTS transacoes (
 id INTEGER PRIMARY KEY, tipo TEXT NOT NULL, valor INTEGER NOT NULL, data TEXT NOT NULL,
 estado TEXT NOT NULL DEFAULT 'efetivada', original_id INTEGER UNIQUE REFERENCES transacoes(id)
);
CREATE TABLE IF NOT EXISTS lancamentos (
 transacao_id INTEGER NOT NULL REFERENCES transacoes(id),
 conta_id INTEGER NOT NULL REFERENCES contas(id), valor INTEGER NOT NULL,
 PRIMARY KEY (transacao_id, conta_id)
);
CREATE TABLE IF NOT EXISTS faturas (
 id INTEGER PRIMARY KEY, cartao_id INTEGER NOT NULL REFERENCES cartoes(id),
 mes_referencia TEXT NOT NULL, principal INTEGER NOT NULL, valor INTEGER NOT NULL,
 vencimento TEXT NOT NULL, estado TEXT NOT NULL, paga_em TEXT,
 UNIQUE(cartao_id, mes_referencia)
);
CREATE TABLE IF NOT EXISTS tarifas (
 id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas(id),
 tipo TEXT NOT NULL, valor INTEGER NOT NULL, estado TEXT NOT NULL, categoria TEXT NOT NULL,
 referencia TEXT NOT NULL, transacao_id INTEGER UNIQUE REFERENCES transacoes(id), cobrada_em TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS tarifa_mensal ON tarifas(conta_id, referencia)
 WHERE tipo = 'mensal';
CREATE INDEX IF NOT EXISTS lancamento_conta ON lancamentos(conta_id, transacao_id);
CREATE INDEX IF NOT EXISTS transacao_data ON transacoes(data);
"""


def agora():
    return datetime.now(BANK_TZ)


def centavos(valor):
    return int(valor * 100)


@contextmanager
def banco():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
    finally:
        conn.close()

def iniciar():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def alterar_saldo(db, conta, delta, momento):
    saldo = conta["saldo"] + delta
    negativa_desde = (conta["negativa_desde"] or momento.isoformat()) if saldo < 0 else None
    db.execute("UPDATE contas SET saldo=?, negativa_desde=? WHERE id=?",
               (saldo, negativa_desde, conta["id"]))


def cobrar_tarifas(db, momento, conta_id=None):
    for tarifa in db.execute("""
        SELECT t.id AS tarifa_id, t.valor, c.* FROM tarifas t
        JOIN contas c ON c.id=t.conta_id JOIN clientes p ON p.id=c.cliente_id
        WHERE t.estado='pendente' AND c.estado='ativa' AND p.situacao='ativo'
        AND (? IS NULL OR c.id=?) ORDER BY t.id
    """, (conta_id, conta_id)).fetchall():
        conta = db.execute("SELECT * FROM contas WHERE id=?", (tarifa["id"],)).fetchone()
        if conta["saldo"] - tarifa["valor"] >= -conta["limite_credito"]:
            alterar_saldo(db, conta, -tarifa["valor"], momento)
            db.execute("UPDATE tarifas SET estado='cobrada', cobrada_em=? WHERE id=?",
                       (momento.isoformat(), tarifa["tarifa_id"]))


def atualizar_pendencias(db, momento):
    hoje = momento.date()
    for fatura in db.execute("""
        SELECT f.*, p.categoria FROM faturas f JOIN cartoes k ON k.id=f.cartao_id
        JOIN contas c ON c.id=k.conta_id JOIN clientes p ON p.id=c.cliente_id
        WHERE f.estado != 'paga' AND f.vencimento < ?
    """, (hoje.isoformat(),)).fetchall():
        dias = (hoje - datetime.fromisoformat(fatura["vencimento"]).date()).days
        juros = (fatura["principal"] * RULES[fatura["categoria"]][4] * dias + 1500) // 3000
        db.execute("UPDATE faturas SET estado='atrasada', valor=? WHERE id=?",
                   (fatura["principal"] + juros, fatura["id"]))
        if dias >= 10:
            db.execute("UPDATE cartoes SET estado='bloqueado' WHERE id=? AND estado='ativo'",
                       (fatura["cartao_id"],))

    corte = (momento - timedelta(days=30)).isoformat()
    devedores = "SELECT cliente_id FROM contas WHERE saldo < 0 AND negativa_desde < ?"
    db.execute(f"UPDATE clientes SET situacao='bloqueado' WHERE id IN ({devedores})", (corte,))
    db.execute(f"""UPDATE cartoes SET estado='bloqueado' WHERE estado='ativo'
                AND conta_id IN (SELECT id FROM contas WHERE cliente_id IN ({devedores}))""", (corte,))

    for conta in db.execute("""
        SELECT c.id, p.categoria FROM contas c JOIN clientes p ON p.id=c.cliente_id
        WHERE c.estado != 'encerrada'
    """).fetchall():
        valor = RULES[conta["categoria"]][2]
        db.execute("""INSERT OR IGNORE INTO tarifas(conta_id,tipo,valor,estado,categoria,referencia)
                      VALUES (?, 'mensal', ?, ?, ?, ?)""",
                   (conta["id"], valor, "pendente" if valor else "isenta",
                    conta["categoria"], hoje.strftime("%Y-%m")))
    cobrar_tarifas(db, momento)

