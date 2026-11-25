import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal
import logging
import os
import re
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from banco import (
    BRASIL, agora, alterar_saldo, banco, conflito, conta_com_cliente,
    estornar, exigir_ativa, inicializar, instante, manutencao, movimentar,
    obter, publico,
)

Dinheiro = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Positivo = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Numero = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,32}$")]
Id = Annotated[int, Field(gt=0)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cliente(Entrada):
    nome: Nome
    cpf: str
    email: EmailStr
    categoria: Literal["comum", "premium", "empresarial"]
    situacao: Literal["ativo", "bloqueado"] = "ativo"

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, valor):
        if not re.fullmatch(r"[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}", valor):
            raise ValueError("Informe um CPF válido")
        digitos = re.sub(r"\D", "", valor)
        if len(set(digitos)) == 1:
            raise ValueError("Informe um CPF válido")
        for tamanho in (9, 10):
            soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
            if (soma * 10 % 11) % 10 != int(digitos[tamanho]):
                raise ValueError("Informe um CPF válido")
        return digitos


class DadosConta(Entrada):
    numero: Numero
    tipo: Literal["corrente", "poupanca"]
    limite_credito: Dinheiro = Decimal(0)


class NovaConta(DadosConta):
    cliente_id: Id


class Conta(DadosConta):
    estado: Literal["ativa", "bloqueada", "encerrada"] = "ativa"


class DadosCartao(Entrada):
    numero: Numero
    limite: Dinheiro
    estado: Literal["ativo", "bloqueado", "cancelado"] = "ativo"


class NovoCartao(DadosCartao):
    conta_id: Id


class Movimento(Entrada):
    conta_id: Id
    valor: Positivo


class Transferencia(Entrada):
    origem_id: Id
    destino_id: Id
    valor: Positivo


class Fatura(Entrada):
    mes_referencia: Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]
    vencimento: date
    valor: Positivo
    estado: Literal["aberta", "fechada"] = "fechada"


def atualizar_prazos():
    with banco() as db, db:
        db.execute("BEGIN IMMEDIATE")
        manutencao(db, agora())


async def agenda():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(atualizar_prazos)
        except sqlite3.Error:
            logging.exception("Falha na atualização dos prazos bancários")


@asynccontextmanager
async def lifespan(app):
    tarifa = int(os.getenv("BANCO_TARIFA_TRANSFERENCIA_CENTAVOS", "500"))
    if not 0 < tarifa <= 10**14:
        raise ValueError("BANCO_TARIFA_TRANSFERENCIA_CENTAVOS deve ser um valor positivo em centavos")
    inicializar()
    atualizar_prazos()
    tarefa = asyncio.create_task(agenda())
    try:
        yield
    finally:
        tarefa.cancel()
        with suppress(asyncio.CancelledError):
            await tarefa


app = FastAPI(title="API bancária", lifespan=lifespan)


def sessao():
    atualizar_prazos()
    with banco() as db, db:
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
        except sqlite3.IntegrityError as erro:
            db.rollback()
            raise HTTPException(409, "Registro duplicado ou vinculado a outro recurso") from erro


DB = Annotated[sqlite3.Connection, Depends(sessao, scope="function")]


def centavos(valor):
    return int(valor * 100)


def listar(db, sql, parametros=()):
    return [publico(linha) for linha in db.execute(sql, parametros)]


def gravar(db, tabela, dados, id=None):
    valores = tuple(dados.values())
    if id is None:
        campos = ", ".join(dados)
        marcadores = ", ".join("?" for _ in dados)
        id = db.execute(f"INSERT INTO {tabela} ({campos}) VALUES ({marcadores})", valores).lastrowid
    else:
        campos = ", ".join(f"{campo} = ?" for campo in dados)
        db.execute(f"UPDATE {tabela} SET {campos} WHERE id = ?", (*valores, id))
    return publico(obter(db, tabela, id))


@app.post("/clientes", status_code=201)
def criar_cliente(dados: Cliente, db: DB):
    return gravar(db, "clientes", dados.model_dump())


@app.get("/clientes")
def listar_clientes(db: DB):
    return listar(db, "SELECT * FROM clientes ORDER BY id")


@app.get("/clientes/{id}")
def ler_cliente(id: int, db: DB):
    return publico(obter(db, "clientes", id))


@app.put("/clientes/{id}")
def editar_cliente(id: int, dados: Cliente, db: DB):
    obter(db, "clientes", id)
    if dados.situacao == "ativo" and db.execute(
        "SELECT 1 FROM contas WHERE cliente_id = ? AND saldo < 0 AND negativo_desde < ?",
        (id, instante(agora() - timedelta(days=30))),
    ).fetchone():
        conflito("O cliente ainda possui saldo negativo há mais de 30 dias")
    if dados.situacao == "bloqueado":
        db.execute(
            """UPDATE cartoes SET estado = 'bloqueado' WHERE estado = 'ativo'
               AND conta_id IN (SELECT id FROM contas WHERE cliente_id = ?)""", (id,)
        )
    return gravar(db, "clientes", dados.model_dump(), id)


@app.delete("/clientes/{id}", status_code=204)
def excluir_cliente(id: int, db: DB):
    obter(db, "clientes", id)
    db.execute("DELETE FROM clientes WHERE id = ?", (id,))
    return Response(status_code=204)


@app.post("/contas", status_code=201)
def criar_conta(dados: NovaConta, db: DB):
    obter(db, "clientes", dados.cliente_id)
    return gravar(db, "contas", dados.model_dump() | {"limite_credito": centavos(dados.limite_credito)})


@app.get("/contas")
def listar_contas(db: DB, cliente_id: int | None = None):
    return listar(db, "SELECT * FROM contas WHERE (? IS NULL OR cliente_id = ?) ORDER BY id",
                  (cliente_id, cliente_id))


@app.get("/contas/{id}")
def ler_conta(id: int, db: DB):
    return publico(obter(db, "contas", id))


def encerrar_conta(db, conta):
    if conta["saldo"] != 0:
        conflito("O encerramento exige saldo zero")
    if db.execute(
        """SELECT 1 FROM faturas JOIN cartoes ON cartoes.id = faturas.cartao_id
           WHERE cartoes.conta_id = ? AND faturas.estado != 'paga'""",
        (conta["id"],),
    ).fetchone():
        conflito("O encerramento exige a quitação das faturas")
    db.execute("UPDATE cartoes SET estado = 'cancelado' WHERE conta_id = ?", (conta["id"],))
    db.execute("UPDATE contas SET estado = 'encerrada' WHERE id = ?", (conta["id"],))


@app.put("/contas/{id}")
def editar_conta(id: int, dados: Conta, db: DB):
    conta = obter(db, "contas", id)
    if conta["estado"] == "encerrada":
        conflito("A conta está encerrada")
    limite = centavos(dados.limite_credito)
    if conta["saldo"] < -limite:
        conflito("O novo limite de crédito é inferior ao saldo devedor")
    if dados.estado == "encerrada":
        encerrar_conta(db, conta)
    return gravar(db, "contas", dados.model_dump() | {"limite_credito": limite}, id)


@app.delete("/contas/{id}", status_code=204)
def excluir_conta(id: int, db: DB):
    encerrar_conta(db, obter(db, "contas", id))
    return Response(status_code=204)


def validar_estado_cartao(db, conta_id, estado, cartao_id=None):
    conta = conta_com_cliente(db, conta_id)
    if conta["estado"] == "encerrada":
        conflito("A conta está encerrada")
    if estado == "ativo":
        exigir_ativa(conta)
        if db.execute(
            """SELECT 1 FROM faturas WHERE cartao_id = ? AND estado = 'atrasada'
               AND vencimento <= ?""",
            (cartao_id, (agora().date() - timedelta(days=10)).isoformat()),
        ).fetchone():
            conflito("O cartão possui fatura com pelo menos 10 dias de atraso")


@app.post("/cartoes", status_code=201)
def criar_cartao(dados: NovoCartao, db: DB):
    validar_estado_cartao(db, dados.conta_id, dados.estado)
    return gravar(db, "cartoes", dados.model_dump() | {"limite": centavos(dados.limite)})


@app.get("/cartoes")
def listar_cartoes(db: DB, conta_id: int | None = None):
    return listar(db, "SELECT * FROM cartoes WHERE (? IS NULL OR conta_id = ?) ORDER BY id",
                  (conta_id, conta_id))


@app.get("/cartoes/{id}")
def ler_cartao(id: int, db: DB):
    return publico(obter(db, "cartoes", id))


@app.put("/cartoes/{id}")
def editar_cartao(id: int, dados: DadosCartao, db: DB):
    cartao = obter(db, "cartoes", id)
    if cartao["estado"] == "cancelado":
        conflito("O cartão está cancelado")
    validar_estado_cartao(db, cartao["conta_id"], dados.estado, id)
    return gravar(db, "cartoes", dados.model_dump() | {"limite": centavos(dados.limite)}, id)


@app.delete("/cartoes/{id}", status_code=204)
def excluir_cartao(id: int, db: DB):
    obter(db, "cartoes", id)
    db.execute("UPDATE cartoes SET estado = 'cancelado' WHERE id = ?", (id,))
    return Response(status_code=204)


@app.post("/transacoes/deposito", status_code=201)
def deposito(dados: Movimento, db: DB):
    return movimentar(db, "deposito", dados.conta_id, centavos(dados.valor), agora())


@app.post("/transacoes/saque", status_code=201)
def saque(dados: Movimento, db: DB):
    return movimentar(db, "saque", dados.conta_id, centavos(dados.valor), agora())


@app.post("/transacoes/transferencia", status_code=201)
def transferencia(dados: Transferencia, db: DB):
    return movimentar(db, "transferencia", dados.origem_id, centavos(dados.valor), agora(), dados.destino_id)


@app.post("/transacoes/{id}/estorno", status_code=201)
def estorno(id: int, db: DB):
    return estornar(db, id, agora())


@app.get("/contas/{id}/extrato")
def extrato(id: int, db: DB):
    obter(db, "contas", id)
    return listar(db, """SELECT * FROM transacoes WHERE conta_id = ? OR destino_id = ?
                         ORDER BY data DESC, id DESC""", (id, id))


@app.post("/cartoes/{id}/faturas", status_code=201)
def emitir_fatura(id: int, dados: Fatura, db: DB):
    cartao = obter(db, "cartoes", id)
    if cartao["estado"] == "cancelado":
        conflito("O cartão está cancelado")
    fatura = gravar(db, "faturas", dados.model_dump() | {
        "cartao_id": id, "vencimento": dados.vencimento.isoformat(), "valor": centavos(dados.valor),
    })
    manutencao(db, agora())
    return publico(obter(db, "faturas", fatura["id"]))


@app.get("/cartoes/{id}/faturas")
def listar_faturas(id: int, db: DB):
    obter(db, "cartoes", id)
    return listar(db, """SELECT *, valor + juros AS total FROM faturas
                         WHERE cartao_id = ? ORDER BY mes_referencia DESC""", (id,))


@app.post("/faturas/{id}/fechamento")
def fechar_fatura(id: int, db: DB):
    fatura = obter(db, "faturas", id)
    if fatura["estado"] != "aberta":
        conflito("Somente faturas abertas podem ser fechadas")
    return gravar(db, "faturas", {"estado": "fechada"}, id)


@app.post("/faturas/{id}/pagamento")
def pagar_fatura(id: int, db: DB):
    fatura = obter(db, "faturas", id)
    if fatura["estado"] not in ("fechada", "atrasada"):
        conflito("Somente faturas fechadas ou atrasadas podem ser pagas")
    cartao = obter(db, "cartoes", fatura["cartao_id"])
    conta = obter(db, "contas", cartao["conta_id"])
    data = agora()
    alterar_saldo(db, conta, -(fatura["valor"] + fatura["juros"]), data)
    return gravar(db, "faturas", {"estado": "paga", "paga_em": instante(data)}, id)


@app.get("/contas/{id}/tarifas")
def listar_tarifas(id: int, db: DB):
    obter(db, "contas", id)
    return listar(db, "SELECT * FROM tarifas WHERE conta_id = ? ORDER BY id", (id,))


def periodo(inicio, fim):
    if inicio > fim:
        raise HTTPException(422, "A data inicial deve ser anterior ou igual à data final")
    return tuple(instante(datetime.combine(dia, hora, BRASIL))
                 for dia, hora in ((inicio, time.min), (fim, time.max)))


@app.get("/relatorios/clientes-maior-movimentacao")
def maior_movimentacao(inicio: date, fim: date, db: DB):
    return listar(db, """
        WITH movimentos AS (
            SELECT c.cliente_id, t.valor FROM transacoes t JOIN contas c ON c.id = t.conta_id
            WHERE t.data BETWEEN ? AND ? AND t.estado = 'efetivada' AND t.tipo != 'estorno'
            UNION ALL
            SELECT d.cliente_id, t.valor FROM transacoes t
            JOIN contas d ON d.id = t.destino_id JOIN contas o ON o.id = t.conta_id
            WHERE t.data BETWEEN ? AND ? AND t.estado = 'efetivada' AND o.cliente_id != d.cliente_id
        )
        SELECT clientes.id AS cliente_id, clientes.nome, SUM(movimentos.valor) AS total
        FROM movimentos JOIN clientes ON clientes.id = movimentos.cliente_id
        GROUP BY clientes.id ORDER BY total DESC, clientes.id
    """, periodo(inicio, fim) * 2)


@app.get("/relatorios/contas-saldo-negativo")
def contas_negativas(db: DB):
    return listar(db, "SELECT * FROM contas WHERE saldo < 0 ORDER BY saldo, id")


@app.get("/relatorios/receita-tarifas")
def receita_tarifas(db: DB, inicio: date | None = None, fim: date | None = None):
    return listar(db, """
        WITH categorias(categoria) AS (VALUES ('comum'), ('premium'), ('empresarial'))
        SELECT categorias.categoria, COALESCE(SUM(tarifas.valor), 0) AS total
        FROM categorias LEFT JOIN tarifas ON tarifas.categoria = categorias.categoria
          AND tarifas.estado = 'cobrada' AND tarifas.cobrada_em BETWEEN ? AND ?
        GROUP BY categorias.categoria ORDER BY categorias.categoria
    """, periodo(inicio or date.min, fim or date.max))

