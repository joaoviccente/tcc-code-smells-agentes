import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
import os
from pathlib import Path
import re
import sqlite3
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

FUSO = timezone(timedelta(hours=-3), "Brasilia")
BANCO = os.getenv("BANCO_DB", str(Path(__file__).with_name("banco.sqlite3")))
TARIFA_TRANSFERENCIA = int(os.getenv("TARIFA_TRANSFERENCIA_CENTAVOS", "500"))
if not 0 < TARIFA_TRANSFERENCIA <= 999_999_999_999:
    raise ValueError("TARIFA_TRANSFERENCIA_CENTAVOS fora do intervalo permitido")

# Saque diário, transferência por operação, mensalidade, franquia e juros (%).
CATEGORIAS = {
    "comum": (100_000, 500_000, 3_000, 3, 8),
    "premium": (500_000, 5_000_000, 0, None, 5),
    "empresarial": (2_000_000, 20_000_000, 12_000, 50, 3),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
    cpf TEXT NOT NULL UNIQUE, email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    categoria TEXT NOT NULL, situacao TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    numero TEXT NOT NULL UNIQUE, tipo TEXT NOT NULL, saldo INTEGER NOT NULL DEFAULT 0,
    limite_credito INTEGER NOT NULL, estado TEXT NOT NULL, negativo_desde TEXT
);
CREATE TABLE IF NOT EXISTS transacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conta_id INTEGER NOT NULL REFERENCES contas(id),
    destino_id INTEGER REFERENCES contas(id), tipo TEXT NOT NULL, valor INTEGER NOT NULL,
    data TEXT NOT NULL, estado TEXT NOT NULL,
    original_id INTEGER UNIQUE REFERENCES transacoes(id)
);
CREATE TABLE IF NOT EXISTS cartoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conta_id INTEGER NOT NULL REFERENCES contas(id),
    numero TEXT NOT NULL UNIQUE, limite INTEGER NOT NULL, estado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS faturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cartao_id INTEGER NOT NULL REFERENCES cartoes(id),
    mes_referencia TEXT NOT NULL, valor INTEGER NOT NULL, juros INTEGER NOT NULL DEFAULT 0,
    vencimento TEXT NOT NULL, estado TEXT NOT NULL, taxa_atraso INTEGER,
    paga_em TEXT, UNIQUE(cartao_id, mes_referencia)
);
CREATE TABLE IF NOT EXISTS tarifas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conta_id INTEGER NOT NULL REFERENCES contas(id),
    tipo TEXT NOT NULL, valor INTEGER NOT NULL, estado TEXT NOT NULL, categoria TEXT NOT NULL,
    competencia TEXT NOT NULL, transacao_id INTEGER UNIQUE REFERENCES transacoes(id),
    cobrada_em TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS mensalidade_unica ON tarifas(conta_id, competencia)
    WHERE tipo = 'mensal';
CREATE INDEX IF NOT EXISTS transacao_origem_data ON transacoes(conta_id, data);
CREATE INDEX IF NOT EXISTS transacao_destino_data ON transacoes(destino_id, data);
CREATE INDEX IF NOT EXISTS contas_cliente ON contas(cliente_id);
CREATE INDEX IF NOT EXISTS cartoes_conta ON cartoes(conta_id);
"""


def conectar():
    db = sqlite3.connect(BANCO, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


@asynccontextmanager
async def lifespan(app):
    db = conectar()
    try:
        db.executescript(SCHEMA)
    finally:
        db.close()
    tarefa = asyncio.create_task(manutencao_periodica())
    try:
        yield
    finally:
        tarefa.cancel()
        with suppress(asyncio.CancelledError):
            await tarefa


app = FastAPI(title="API de contas bancárias", lifespan=lifespan)


def agora():
    return datetime.now(timezone.utc)


def local(instante):
    return instante.astimezone(FUSO)


def conflito(mensagem):
    raise HTTPException(409, mensagem)


def registro(db, tabela, id):
    item = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id,)).fetchone()
    if item is None:
        raise HTTPException(404, "Registro não encontrado")
    return item


def publicar(item):
    dados = dict(item)
    for campo in ("saldo", "limite_credito", "valor", "limite", "juros", "movimentacao", "receita"):
        if campo in dados:
            dados[campo] = format(Decimal(dados[campo]) / 100, ".2f")
    dados.pop("taxa_atraso", None)
    return dados


def listar(db, sql, params=()):
    return [publicar(item) for item in db.execute(sql, params)]


def inserir(db, tabela, dados):
    campos = ", ".join(dados)
    marcadores = ", ".join("?" for _ in dados)
    return db.execute(
        f"INSERT INTO {tabela} ({campos}) VALUES ({marcadores})", tuple(dados.values())
    ).lastrowid


def atualizar(db, tabela, id, dados):
    if dados:
        campos = ", ".join(f"{campo} = ?" for campo in dados)
        db.execute(f"UPDATE {tabela} SET {campos} WHERE id = ?", (*dados.values(), id))
    return publicar(registro(db, tabela, id))


def alterar_saldo(db, conta, delta, instante):
    saldo = conta["saldo"] + delta
    if saldo < -conta["limite_credito"]:
        conflito("Saldo e limite de crédito insuficientes")
    desde = None
    if saldo < 0:
        desde = conta["negativo_desde"] or instante.isoformat(timespec="microseconds")
    db.execute(
        "UPDATE contas SET saldo = ?, negativo_desde = ? WHERE id = ?",
        (saldo, desde, conta["id"]),
    )


def cliente_conta(db, conta):
    return registro(db, "clientes", conta["cliente_id"])


def exigir_ativa(db, conta):
    cliente = cliente_conta(db, conta)
    if conta["estado"] != "ativa" or cliente["situacao"] != "ativo":
        conflito("A operação exige conta e cliente ativos")
    return cliente


def bloquear_cliente(db, cliente_id):
    db.execute("UPDATE clientes SET situacao = 'bloqueado' WHERE id = ?", (cliente_id,))
    db.execute("""
        UPDATE cartoes SET estado = 'bloqueado' WHERE estado = 'ativo'
        AND conta_id IN (SELECT id FROM contas WHERE cliente_id = ?)
    """, (cliente_id,))


def manutencao(db, instante):
    hoje = local(instante).date()
    mes = hoje.isoformat()[:7]
    for cliente in db.execute("""
        SELECT DISTINCT cliente_id FROM contas WHERE saldo < 0
        AND negativo_desde < ?
    """, ((instante - timedelta(days=30)).isoformat(timespec="microseconds"),)).fetchall():
        bloquear_cliente(db, cliente["cliente_id"])

    for conta in db.execute("""
        SELECT a.*, c.categoria FROM contas a JOIN clientes c ON c.id = a.cliente_id
        WHERE a.estado = 'ativa' AND c.situacao = 'ativo'
    """).fetchall():
        valor = CATEGORIAS[conta["categoria"]][2]
        db.execute("""
            INSERT OR IGNORE INTO tarifas (conta_id, tipo, valor, estado, categoria, competencia)
            VALUES (?, 'mensal', ?, ?, ?, ?)
        """, (conta["id"], valor, "pendente" if valor else "isenta", conta["categoria"], mes))

    for tarifa in db.execute("""
        SELECT t.* FROM tarifas t JOIN contas a ON a.id = t.conta_id
        JOIN clientes c ON c.id = a.cliente_id WHERE t.estado = 'pendente'
        AND a.estado = 'ativa' AND c.situacao = 'ativo' ORDER BY t.id
    """).fetchall():
        conta = registro(db, "contas", tarifa["conta_id"])
        if conta["saldo"] + conta["limite_credito"] >= tarifa["valor"]:
            alterar_saldo(db, conta, -tarifa["valor"], instante)
            atualizar(db, "tarifas", tarifa["id"], {
                "estado": "cobrada", "cobrada_em": instante.isoformat(timespec="microseconds"),
            })

    faturas = db.execute("""
        SELECT f.*, c.categoria FROM faturas f JOIN cartoes k ON k.id = f.cartao_id
        JOIN contas a ON a.id = k.conta_id JOIN clientes c ON c.id = a.cliente_id
        WHERE f.estado <> 'paga' AND f.vencimento < ?
    """, (hoje.isoformat(),)).fetchall()
    for fatura in faturas:
        dias = (hoje - date.fromisoformat(fatura["vencimento"])).days
        taxa = fatura["taxa_atraso"] or CATEGORIAS[fatura["categoria"]][4]
        juros = int((Decimal(fatura["valor"] * taxa * dias) / 3000).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ))
        atualizar(db, "faturas", fatura["id"], {
            "estado": "atrasada", "juros": juros, "taxa_atraso": taxa,
        })
        if dias >= 10:
            db.execute("""
                UPDATE cartoes SET estado = 'bloqueado' WHERE id = ? AND estado = 'ativo'
            """, (fatura["cartao_id"],))


def executar_manutencao(db):
    db.execute("BEGIN IMMEDIATE")
    manutencao(db, agora())
    db.commit()


def ciclo_manutencao():
    db = conectar()
    try:
        executar_manutencao(db)
    finally:
        db.close()


async def manutencao_periodica():
    while True:
        try:
            await asyncio.to_thread(ciclo_manutencao)
        except sqlite3.Error:
            logging.getLogger(__name__).exception("Falha na manutencao bancaria")
        await asyncio.sleep(60)


def sessao():
    db = conectar()
    try:
        executar_manutencao(db)
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except sqlite3.IntegrityError as erro:
        db.rollback()
        raise HTTPException(409, "Registro duplicado ou vinculado a outro registro") from erro
    except sqlite3.OperationalError as erro:
        if erro.sqlite_errorcode in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise HTTPException(503, "Banco temporariamente ocupado") from erro
        raise
    finally:
        db.close()


DB = Annotated[sqlite3.Connection, Depends(sessao, scope="function")]
Id = Annotated[int, Field(gt=0, le=2**63 - 1)]
Dinheiro = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Valor = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Numero = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,32}$")]
Categoria = Literal["comum", "premium", "empresarial"]
Situacao = Literal["ativo", "bloqueado"]
TipoConta = Literal["corrente", "poupanca"]
EstadoConta = Literal["ativa", "bloqueada", "encerrada"]
EstadoCartao = Literal["ativo", "bloqueado", "cancelado"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def rejeitar_nulo(cls, valor):
        if valor is None:
            raise ValueError("Informe um valor ou omita o campo")
        return valor


class AlterarCliente(Entrada):
    nome: Nome | None = None
    cpf: str | None = None
    email: str | None = None
    categoria: Categoria | None = None
    situacao: Situacao | None = None

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, cpf):
        if not re.fullmatch(r"(?:[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2})", cpf):
            raise ValueError("CPF deve ter 11 dígitos")
        cpf = re.sub(r"[.-]", "", cpf)
        if len(set(cpf)) == 1 or any(
            (sum(int(n) * peso for n, peso in zip(cpf[:i], range(i + 1, 1, -1))) * 10)
            % 11 % 10 != int(cpf[i]) for i in (9, 10)
        ):
            raise ValueError("CPF inválido")
        return cpf

    @field_validator("email")
    @classmethod
    def validar_email(cls, email):
        email = email.strip()
        if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", email):
            raise ValueError("E-mail inválido")
        return email


class NovoCliente(AlterarCliente):
    nome: Nome
    cpf: str
    email: str
    categoria: Categoria
    situacao: Situacao = "ativo"


class AlterarConta(Entrada):
    numero: Numero | None = None
    tipo: TipoConta | None = None
    limite_credito: Dinheiro | None = None
    estado: EstadoConta | None = None


class NovaConta(AlterarConta):
    cliente_id: Id
    numero: Numero
    tipo: TipoConta
    limite_credito: Dinheiro = Decimal(0)
    estado: Literal["ativa", "bloqueada"] = "ativa"


class AlterarCartao(Entrada):
    numero: Numero | None = None
    limite: Dinheiro | None = None
    estado: EstadoCartao | None = None


class NovoCartao(AlterarCartao):
    conta_id: Id
    numero: Numero
    limite: Dinheiro
    estado: Situacao = "ativo"


class Operacao(Entrada):
    conta_id: Id
    valor: Valor


class Transferencia(Operacao):
    destino_id: Id


class NovaFatura(Entrada):
    mes_referencia: Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]
    valor: Valor
    vencimento: date
    estado: Literal["aberta", "fechada"] = "aberta"

    @field_validator("mes_referencia")
    @classmethod
    def validar_mes(cls, mes):
        date.fromisoformat(mes + "-01")
        return mes


def centavos(valor):
    return int(valor * 100)


def campos(modelo):
    return {
        campo: centavos(valor) if isinstance(valor, Decimal) else valor
        for campo, valor in modelo.model_dump(exclude_unset=True).items()
    }


@app.post("/clientes", status_code=201)
def criar_cliente(entrada: NovoCliente, db: DB):
    id = inserir(db, "clientes", entrada.model_dump())
    return publicar(registro(db, "clientes", id))


@app.get("/clientes")
def listar_clientes(db: DB):
    return listar(db, "SELECT * FROM clientes ORDER BY id")


@app.get("/clientes/{id}")
def consultar_cliente(id: Id, db: DB):
    return publicar(registro(db, "clientes", id))


@app.patch("/clientes/{id}")
def editar_cliente(id: Id, entrada: AlterarCliente, db: DB):
    registro(db, "clientes", id)
    dados = campos(entrada)
    if dados.get("situacao") == "ativo" and db.execute("""
        SELECT 1 FROM contas WHERE cliente_id = ? AND saldo < 0
        AND negativo_desde < ?
    """, (id, (agora() - timedelta(days=30)).isoformat(timespec="microseconds"))).fetchone():
        conflito("Cliente possui conta com saldo negativo há mais de 30 dias")
    return atualizar(db, "clientes", id, dados)


@app.delete("/clientes/{id}", status_code=204)
def excluir_cliente(id: Id, db: DB):
    registro(db, "clientes", id)
    db.execute("DELETE FROM clientes WHERE id = ?", (id,))


@app.post("/contas", status_code=201)
def criar_conta(entrada: NovaConta, db: DB):
    cliente = registro(db, "clientes", entrada.cliente_id)
    if cliente["situacao"] == "bloqueado" and entrada.estado == "ativa":
        conflito("Cliente bloqueado")
    dados = campos(entrada)
    dados.setdefault("limite_credito", 0)
    dados.setdefault("estado", "ativa")
    id = inserir(db, "contas", dados)
    return publicar(registro(db, "contas", id))


@app.get("/contas")
def listar_contas(db: DB, cliente_id: Annotated[Id | None, Query()] = None):
    if cliente_id is not None:
        registro(db, "clientes", cliente_id)
        return listar(db, "SELECT * FROM contas WHERE cliente_id = ? ORDER BY id", (cliente_id,))
    return listar(db, "SELECT * FROM contas ORDER BY id")


@app.get("/contas/{id}")
def consultar_conta(id: Id, db: DB):
    return publicar(registro(db, "contas", id))


def encerrar_conta(db, conta):
    if conta["saldo"]:
        conflito("O encerramento exige saldo zero")
    if db.execute("""
        SELECT 1 FROM faturas f JOIN cartoes k ON k.id = f.cartao_id
        WHERE k.conta_id = ? AND f.estado <> 'paga'
    """, (conta["id"],)).fetchone():
        conflito("O encerramento exige quitação das faturas")
    db.execute("UPDATE cartoes SET estado = 'cancelado' WHERE conta_id = ?", (conta["id"],))


@app.patch("/contas/{id}")
def editar_conta(id: Id, entrada: AlterarConta, db: DB):
    conta = registro(db, "contas", id)
    dados = campos(entrada)
    if conta["estado"] == "encerrada" and dados:
        conflito("Conta encerrada")
    if conta["saldo"] < -dados.get("limite_credito", conta["limite_credito"]):
        conflito("Limite inferior ao crédito utilizado")
    if dados.get("estado") == "ativa" and cliente_conta(db, conta)["situacao"] != "ativo":
        conflito("Cliente bloqueado")
    if dados.get("estado") == "encerrada":
        encerrar_conta(db, conta)
    return atualizar(db, "contas", id, dados)


@app.delete("/contas/{id}", status_code=204)
def excluir_conta(id: Id, db: DB):
    conta = registro(db, "contas", id)
    encerrar_conta(db, conta)
    atualizar(db, "contas", id, {"estado": "encerrada"})


@app.post("/cartoes", status_code=201)
def criar_cartao(entrada: NovoCartao, db: DB):
    exigir_ativa(db, registro(db, "contas", entrada.conta_id))
    dados = campos(entrada)
    dados.setdefault("estado", "ativo")
    id = inserir(db, "cartoes", dados)
    return publicar(registro(db, "cartoes", id))


@app.get("/cartoes")
def listar_cartoes(db: DB, conta_id: Annotated[Id | None, Query()] = None):
    if conta_id is not None:
        registro(db, "contas", conta_id)
        return listar(db, "SELECT * FROM cartoes WHERE conta_id = ? ORDER BY id", (conta_id,))
    return listar(db, "SELECT * FROM cartoes ORDER BY id")


@app.get("/cartoes/{id}")
def consultar_cartao(id: Id, db: DB):
    return publicar(registro(db, "cartoes", id))


@app.patch("/cartoes/{id}")
def editar_cartao(id: Id, entrada: AlterarCartao, db: DB):
    cartao = registro(db, "cartoes", id)
    dados = campos(entrada)
    if cartao["estado"] == "cancelado" and dados:
        conflito("Cartão cancelado")
    if dados.get("estado") == "ativo":
        exigir_ativa(db, registro(db, "contas", cartao["conta_id"]))
        if db.execute("""
            SELECT 1 FROM faturas WHERE cartao_id = ? AND estado = 'atrasada'
            AND julianday(?) - julianday(vencimento) >= 10
        """, (id, local(agora()).date().isoformat())).fetchone():
            conflito("Cartão possui fatura com pelo menos 10 dias de atraso")
    return atualizar(db, "cartoes", id, dados)


@app.delete("/cartoes/{id}", status_code=204)
def excluir_cartao(id: Id, db: DB):
    atualizar(db, "cartoes", id, {"estado": "cancelado"})


def transacao(db, conta_id, tipo, valor, instante, destino_id=None, original_id=None):
    return inserir(db, "transacoes", {
        "conta_id": conta_id, "tipo": tipo, "valor": valor, "data": instante.isoformat(timespec="microseconds"),
        "destino_id": destino_id, "original_id": original_id, "estado": "efetivada",
    })


def nao_encerrada(conta):
    if conta["estado"] == "encerrada":
        conflito("Conta encerrada")


@app.post("/transacoes/deposito", status_code=201)
def depositar(entrada: Operacao, db: DB):
    conta = registro(db, "contas", entrada.conta_id)
    nao_encerrada(conta)
    valor, instante = centavos(entrada.valor), agora()
    alterar_saldo(db, conta, valor, instante)
    id = transacao(db, conta["id"], "deposito", valor, instante)
    return publicar(registro(db, "transacoes", id))


@app.post("/transacoes/saque", status_code=201)
def sacar(entrada: Operacao, db: DB):
    conta = registro(db, "contas", entrada.conta_id)
    cliente = exigir_ativa(db, conta)
    valor, instante = centavos(entrada.valor), agora()
    inicio = local(instante).replace(hour=0, minute=0, second=0, microsecond=0)
    total = db.execute("""
        SELECT COALESCE(SUM(t.valor), 0) FROM transacoes t JOIN contas a ON a.id = t.conta_id
        WHERE a.cliente_id = ? AND t.tipo = 'saque' AND t.estado = 'efetivada' AND t.data >= ?
    """, (cliente["id"], inicio.astimezone(timezone.utc).isoformat())).fetchone()[0]
    if total + valor > CATEGORIAS[cliente["categoria"]][0]:
        conflito("Limite diário de saque excedido")
    alterar_saldo(db, conta, -valor, instante)
    id = transacao(db, conta["id"], "saque", valor, instante)
    return publicar(registro(db, "transacoes", id))


@app.post("/transacoes/transferencia", status_code=201)
def transferir(entrada: Transferencia, db: DB):
    origem = registro(db, "contas", entrada.conta_id)
    destino = registro(db, "contas", entrada.destino_id)
    cliente = exigir_ativa(db, origem)
    exigir_ativa(db, destino)
    if origem["id"] == destino["id"]:
        conflito("As contas de origem e destino devem ser diferentes")
    valor, instante = centavos(entrada.valor), agora()
    categoria = cliente["categoria"]
    _, limite, _, franquia, _ = CATEGORIAS[categoria]
    if valor > limite:
        conflito("Limite por transferência excedido")
    mes = local(instante).date().isoformat()[:7]
    tarifa = 0
    if origem["cliente_id"] != destino["cliente_id"] and franquia is not None:
        consumo = db.execute("""
            SELECT COUNT(*) FROM tarifas t JOIN contas a ON a.id = t.conta_id
            JOIN transacoes x ON x.id = t.transacao_id JOIN contas d ON d.id = x.destino_id
            WHERE a.cliente_id = ? AND d.cliente_id <> a.cliente_id
            AND t.competencia = ? AND x.estado = 'efetivada'
        """, (cliente["id"], mes)).fetchone()[0]
        if consumo >= franquia:
            tarifa = TARIFA_TRANSFERENCIA
    alterar_saldo(db, origem, -valor - tarifa, instante)
    alterar_saldo(db, destino, valor, instante)
    id = transacao(db, origem["id"], "transferencia", valor, instante, destino["id"])
    inserir(db, "tarifas", {
        "conta_id": origem["id"], "tipo": "transferencia", "valor": tarifa,
        "estado": "cobrada" if tarifa else "isenta", "categoria": categoria,
        "competencia": mes, "transacao_id": id,
        "cobrada_em": instante.isoformat(timespec="microseconds") if tarifa else None,
    })
    return publicar(registro(db, "transacoes", id))


@app.post("/transacoes/{id}/estorno", status_code=201)
def estornar(id: Id, db: DB):
    original = registro(db, "transacoes", id)
    instante = agora()
    if original["estado"] != "efetivada" or original["tipo"] == "estorno":
        conflito("A transação não pode ser estornada")
    if (instante - datetime.fromisoformat(original["data"])).total_seconds() > 86_400:
        conflito("Prazo de 24 horas para estorno excedido")
    conta = registro(db, "contas", original["conta_id"])
    nao_encerrada(conta)
    valor = original["valor"]
    delta = -valor if original["tipo"] == "deposito" else valor
    tarifa = db.execute("SELECT * FROM tarifas WHERE transacao_id = ?", (id,)).fetchone()
    if tarifa and tarifa["estado"] == "cobrada":
        delta += tarifa["valor"]
        atualizar(db, "tarifas", tarifa["id"], {"estado": "isenta", "cobrada_em": None})
    if original["destino_id"] is not None:
        destino = registro(db, "contas", original["destino_id"])
        nao_encerrada(destino)
        alterar_saldo(db, destino, -valor, instante)
    alterar_saldo(db, conta, delta, instante)
    atualizar(db, "transacoes", id, {"estado": "estornada"})
    novo_id = transacao(db, conta["id"], "estorno", valor, instante, original["destino_id"], id)
    return publicar(registro(db, "transacoes", novo_id))


@app.get("/contas/{id}/extrato")
def extrato(id: Id, db: DB):
    registro(db, "contas", id)
    return listar(db, """
        SELECT * FROM transacoes WHERE conta_id = ? OR destino_id = ? ORDER BY data DESC, id DESC
    """, (id, id))


@app.get("/cartoes/{id}/faturas")
def listar_faturas(id: Id, db: DB):
    registro(db, "cartoes", id)
    return listar(db, "SELECT * FROM faturas WHERE cartao_id = ? ORDER BY mes_referencia DESC", (id,))


@app.post("/cartoes/{id}/faturas", status_code=201)
def criar_fatura(id: Id, entrada: NovaFatura, db: DB):
    cartao = registro(db, "cartoes", id)
    if cartao["estado"] == "cancelado":
        conflito("Cartão cancelado")
    dados = campos(entrada)
    dados.setdefault("estado", "aberta")
    dados.update(cartao_id=id, vencimento=entrada.vencimento.isoformat())
    fatura_id = inserir(db, "faturas", dados)
    manutencao(db, agora())
    return publicar(registro(db, "faturas", fatura_id))


@app.post("/faturas/{id}/fechamento")
def fechar_fatura(id: Id, db: DB):
    if registro(db, "faturas", id)["estado"] != "aberta":
        conflito("Somente faturas abertas podem ser fechadas")
    return atualizar(db, "faturas", id, {"estado": "fechada"})


@app.post("/faturas/{id}/pagamento")
def pagar_fatura(id: Id, db: DB):
    fatura = registro(db, "faturas", id)
    if fatura["estado"] == "paga":
        conflito("Fatura já paga")
    cartao = registro(db, "cartoes", fatura["cartao_id"])
    conta = registro(db, "contas", cartao["conta_id"])
    nao_encerrada(conta)
    instante = agora()
    alterar_saldo(db, conta, -fatura["valor"] - fatura["juros"], instante)
    return atualizar(db, "faturas", id, {"estado": "paga", "paga_em": instante.isoformat()})


@app.get("/contas/{id}/tarifas")
def listar_tarifas(id: Id, db: DB):
    registro(db, "contas", id)
    return listar(db, "SELECT * FROM tarifas WHERE conta_id = ? ORDER BY id DESC", (id,))


def periodo(inicio, fim):
    if inicio > fim:
        raise HTTPException(422, "Início do período deve ser anterior ou igual ao fim")
    # As datas são inclusivas e interpretadas no fuso bancário.
    primeiro = datetime.combine(inicio, datetime.min.time(), FUSO)
    ultimo = (datetime.max.replace(tzinfo=timezone.utc) if fim == date.max
              else datetime.combine(fim, datetime.max.time(), FUSO))
    return tuple(limite.astimezone(timezone.utc).isoformat(timespec="microseconds")
                 for limite in (primeiro, ultimo))


@app.get("/relatorios/clientes-maior-movimentacao")
def maior_movimentacao(
    inicio: date, fim: date, db: DB, limite: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return listar(db, """
        WITH movimentos AS (
            SELECT a.cliente_id, d.cliente_id AS destinatario, t.valor
            FROM transacoes t JOIN contas a ON a.id = t.conta_id
            LEFT JOIN contas d ON d.id = t.destino_id
            WHERE t.estado = 'efetivada' AND t.tipo <> 'estorno' AND t.data BETWEEN ? AND ?
        ), totais AS (
            SELECT cliente_id, valor FROM movimentos UNION ALL
            SELECT destinatario, valor FROM movimentos WHERE destinatario <> cliente_id
        )
        SELECT c.id AS cliente_id, c.nome, SUM(t.valor) AS movimentacao
        FROM totais t JOIN clientes c ON c.id = t.cliente_id
        GROUP BY c.id ORDER BY movimentacao DESC, c.id LIMIT ?
    """, (*periodo(inicio, fim), limite))


@app.get("/relatorios/contas-negativas")
def contas_negativas(db: DB):
    return listar(db, "SELECT * FROM contas WHERE saldo < 0 ORDER BY saldo, id")


@app.get("/relatorios/receita-tarifas")
def receita_tarifas(db: DB, inicio: date | None = None, fim: date | None = None):
    if (inicio is None) != (fim is None):
        raise HTTPException(422, "Informe início e fim juntos")
    filtro = " AND cobrada_em BETWEEN ? AND ?" if inicio is not None else ""
    params = periodo(inicio, fim) if inicio is not None else ()
    receitas = dict(db.execute(f"""
        SELECT categoria, SUM(valor) FROM tarifas WHERE estado = 'cobrada'
        {filtro} GROUP BY categoria
    """, params))
    return [publicar({"categoria": categoria, "receita": receitas.get(categoria, 0)})
            for categoria in CATEGORIAS]
