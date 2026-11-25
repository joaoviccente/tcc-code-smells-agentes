from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import sqlite3

from fastapi import HTTPException

BRASIL = timezone(timedelta(hours=-3))


# Saque diário, transferência, mensalidade, franquia, juros mensais.
CATEGORIAS = {
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
    id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes,
    numero TEXT NOT NULL UNIQUE, tipo TEXT NOT NULL, saldo INTEGER NOT NULL DEFAULT 0,
    limite_credito INTEGER NOT NULL, estado TEXT NOT NULL DEFAULT 'ativa',
    negativo_desde TEXT
);
CREATE TABLE IF NOT EXISTS transacoes (
    id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas,
    destino_id INTEGER REFERENCES contas, original_id INTEGER UNIQUE REFERENCES transacoes,
    tipo TEXT NOT NULL, valor INTEGER NOT NULL, data TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'efetivada', consome_franquia INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS transacoes_conta ON transacoes(conta_id, data);
CREATE INDEX IF NOT EXISTS transacoes_destino ON transacoes(destino_id, data);
CREATE TABLE IF NOT EXISTS cartoes (
    id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas,
    numero TEXT NOT NULL UNIQUE, limite INTEGER NOT NULL, estado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS faturas (
    id INTEGER PRIMARY KEY, cartao_id INTEGER NOT NULL REFERENCES cartoes,
    mes_referencia TEXT NOT NULL, vencimento TEXT NOT NULL, valor INTEGER NOT NULL,
    juros INTEGER NOT NULL DEFAULT 0, estado TEXT NOT NULL,
    paga_em TEXT, UNIQUE(cartao_id, mes_referencia)
);
CREATE TABLE IF NOT EXISTS tarifas (
    id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas,
    transacao_id INTEGER UNIQUE REFERENCES transacoes, tipo TEXT NOT NULL,
    referencia TEXT, categoria TEXT NOT NULL, valor INTEGER NOT NULL, estado TEXT NOT NULL,
    cobrada_em TEXT, UNIQUE(conta_id, tipo, referencia)
);
"""


def agora():
    return datetime.now(BRASIL)


def instante(data):
    return data.isoformat(timespec="microseconds")


@contextmanager
def banco():
    db = sqlite3.connect(os.getenv("BANCO_DB", "banco.sqlite3"), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
    finally:
        db.close()


def inicializar():
    with banco() as db:
        db.executescript(SCHEMA)


def conflito(mensagem):
    raise HTTPException(409, mensagem)


def obter(db, tabela, id):
    linha = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id,)).fetchone()
    if linha is None:
        raise HTTPException(404, "Recurso não encontrado")
    return linha


def publico(linha):
    campos_internos = {"consome_franquia"}
    monetarios = {"saldo", "limite_credito", "limite", "valor", "juros", "total"}
    return {
        chave: format(Decimal(valor) / 100, ".2f") if chave in monetarios else valor
        for chave, valor in dict(linha).items() if chave not in campos_internos
    }


def conta_com_cliente(db, id):
    obter(db, "contas", id)
    return db.execute(
        """SELECT contas.*, clientes.categoria, clientes.situacao
           FROM contas JOIN clientes ON clientes.id = contas.cliente_id WHERE contas.id = ?""",
        (id,),
    ).fetchone()


def exigir_ativa(conta):
    if conta["estado"] != "ativa" or conta["situacao"] != "ativo":
        conflito("A operação exige conta e cliente ativos")


def alterar_saldo(db, conta, variacao, data):
    saldo = conta["saldo"] + variacao
    if saldo < -conta["limite_credito"]:
        conflito("Saldo e limite de crédito insuficientes")
    negativo_desde = (conta["negativo_desde"] or instante(data)) if saldo < 0 else None
    db.execute("UPDATE contas SET saldo = ?, negativo_desde = ? WHERE id = ?",
               (saldo, negativo_desde, conta["id"]))


def cobrar_pendentes(db, data):
    tarifas = db.execute(
        """SELECT tarifas.id, tarifas.conta_id, tarifas.valor
           FROM tarifas JOIN contas ON contas.id = tarifas.conta_id
           JOIN clientes ON clientes.id = contas.cliente_id
           WHERE tarifas.estado = 'pendente' AND contas.estado = 'ativa'
             AND clientes.situacao = 'ativo' ORDER BY tarifas.id"""
    ).fetchall()
    for tarifa in tarifas:
        conta = obter(db, "contas", tarifa["conta_id"])
        if conta["saldo"] - tarifa["valor"] >= -conta["limite_credito"]:
            alterar_saldo(db, conta, -tarifa["valor"], data)
            db.execute("UPDATE tarifas SET estado = 'cobrada', cobrada_em = ? WHERE id = ?",
                       (instante(data), tarifa["id"]))


def manutencao(db, data):
    hoje = data.date()
    db.execute(
        """UPDATE clientes SET situacao = 'bloqueado' WHERE id IN (
           SELECT cliente_id FROM contas WHERE saldo < 0 AND negativo_desde < ?)""",
        (instante(data - timedelta(days=30)),),
    )
    faturas = db.execute(
        """SELECT faturas.id, faturas.valor, faturas.vencimento, clientes.categoria
           FROM faturas JOIN cartoes ON cartoes.id = faturas.cartao_id
           JOIN contas ON contas.id = cartoes.conta_id
           JOIN clientes ON clientes.id = contas.cliente_id
           WHERE faturas.estado != 'paga' AND faturas.vencimento < ?""",
        (hoje.isoformat(),),
    ).fetchall()
    for fatura in faturas:
        dias = (hoje - datetime.fromisoformat(fatura["vencimento"]).date()).days
        taxa = CATEGORIAS[fatura["categoria"]][4]
        juros = (fatura["valor"] * taxa * dias + 1500) // 3000
        db.execute("UPDATE faturas SET estado = 'atrasada', juros = ? WHERE id = ?",
                   (juros, fatura["id"]))
    db.execute(
        """UPDATE cartoes SET estado = 'bloqueado' WHERE estado = 'ativo' AND (
           conta_id IN (SELECT contas.id FROM contas JOIN clientes
              ON clientes.id = contas.cliente_id WHERE clientes.situacao = 'bloqueado')
           OR id IN (SELECT cartao_id FROM faturas WHERE estado = 'atrasada' AND vencimento <= ?))""",
        ((hoje - timedelta(days=10)).isoformat(),),
    )
    db.execute(
        """INSERT OR IGNORE INTO tarifas (conta_id, tipo, referencia, categoria, valor, estado)
           SELECT contas.id, 'mensal', ?, clientes.categoria,
              CASE clientes.categoria WHEN 'comum' THEN ? WHEN 'empresarial' THEN ? ELSE 0 END,
              CASE clientes.categoria WHEN 'premium' THEN 'isenta' ELSE 'pendente' END
           FROM contas JOIN clientes ON clientes.id = contas.cliente_id WHERE contas.estado != 'encerrada'""",
        (hoje.strftime("%Y-%m"), CATEGORIAS["comum"][2], CATEGORIAS["empresarial"][2]),
    )
    cobrar_pendentes(db, data)


def inicio_do_dia(data):
    return instante(data.replace(hour=0, minute=0, second=0, microsecond=0))


def movimentar(db, tipo, conta_id, valor, data, destino_id=None):
    origem = conta_com_cliente(db, conta_id)
    if origem["estado"] == "encerrada":
        conflito("A conta está encerrada")
    destino = None
    if tipo == "transferencia":
        if conta_id == destino_id:
            conflito("As contas de origem e destino devem ser diferentes")
        destino = conta_com_cliente(db, destino_id)
        exigir_ativa(destino)
    if tipo != "deposito":
        exigir_ativa(origem)
        limite = CATEGORIAS[origem["categoria"]][0 if tipo == "saque" else 1]
        acumulado = db.execute(
            """SELECT COALESCE(SUM(transacoes.valor), 0)
               FROM transacoes JOIN contas ON contas.id = transacoes.conta_id
               WHERE contas.cliente_id = ? AND transacoes.tipo = ?
                 AND transacoes.data >= ?""",
            (origem["cliente_id"], tipo, inicio_do_dia(data)),
        ).fetchone()[0]
        if valor > limite or acumulado + valor > limite:
            conflito("Limite da categoria excedido")
    alterar_saldo(db, origem, valor if tipo == "deposito" else -valor, data)
    if destino is not None:
        alterar_saldo(db, destino, valor, data)
    consome = destino is not None and origem["cliente_id"] != destino["cliente_id"]
    transacao = db.execute(
        """INSERT INTO transacoes (conta_id, destino_id, tipo, valor, data, consome_franquia)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (conta_id, destino_id, tipo, valor, instante(data), int(consome)),
    ).lastrowid
    if destino is not None:
        registrar_tarifa_transferencia(db, origem, transacao, data, consome)
    cobrar_pendentes(db, data)
    return publico(obter(db, "transacoes", transacao))


def registrar_tarifa_transferencia(db, conta, transacao, data, consome):
    categoria = conta["categoria"]
    franquia = CATEGORIAS[categoria][3]
    excedeu = False
    if consome and franquia is not None:
        usos = db.execute(
            """SELECT COUNT(*) FROM transacoes JOIN contas ON contas.id = transacoes.conta_id
               WHERE contas.cliente_id = ? AND transacoes.consome_franquia = 1 AND transacoes.data >= ?""",
            (conta["cliente_id"], instante(data.replace(day=1, hour=0, minute=0, second=0, microsecond=0))),
        ).fetchone()[0]
        excedeu = usos > franquia
    valor = int(os.getenv("BANCO_TARIFA_TRANSFERENCIA_CENTAVOS", "500")) if excedeu else 0
    db.execute(
        """INSERT INTO tarifas (conta_id, transacao_id, tipo, categoria, valor, estado)
           VALUES (?, ?, 'transferencia', ?, ?, ?)""",
        (conta["id"], transacao, categoria, valor, "pendente" if excedeu else "isenta"),
    )


def estornar(db, id, data):
    original = obter(db, "transacoes", id)
    if original["estado"] != "efetivada" or original["tipo"] == "estorno":
        conflito("A transação não pode ser estornada")
    if data - datetime.fromisoformat(original["data"]) > timedelta(hours=24):
        conflito("Prazo de 24 horas para estorno excedido")
    origem = obter(db, "contas", original["conta_id"])
    destino = obter(db, "contas", original["destino_id"]) if original["destino_id"] else None
    if origem["estado"] == "encerrada" or (destino and destino["estado"] == "encerrada"):
        conflito("Uma das contas da transação está encerrada")
    valor = original["valor"]
    if destino:
        alterar_saldo(db, destino, -valor, data)
    alterar_saldo(db, origem, -valor if original["tipo"] == "deposito" else valor, data)
    db.execute("UPDATE transacoes SET estado = 'estornada' WHERE id = ?", (id,))
    estorno = db.execute(
        """INSERT INTO transacoes (conta_id, destino_id, original_id, tipo, valor, data)
           VALUES (?, ?, ?, 'estorno', ?, ?)""",
        (origem["id"], original["destino_id"], id, valor, instante(data)),
    ).lastrowid
    return publico(obter(db, "transacoes", estorno))
