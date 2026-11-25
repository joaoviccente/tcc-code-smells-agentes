import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from database import inicializar, unidade
from regras import (agora, centavos, conflito, estornar, exigir_ativa, listar,
                    manutencao, movimentar, obter, publicar, reais, saldo)
from schemas import (CartaoDados, CartaoNovo, ClienteDados, ContaDados, ContaNova,
                     FaturaNova, Movimento, Transferencia)

logger = logging.getLogger(__name__)


def executar_manutencao():
    with unidade() as db:
        manutencao(db, agora())


async def ciclo_manutencao():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(executar_manutencao)
        except sqlite3.Error:
            logger.exception("Falha na manutencao bancaria")


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(inicializar)
    await asyncio.to_thread(executar_manutencao)
    tarefa = asyncio.create_task(ciclo_manutencao())
    try:
        yield
    finally:
        tarefa.cancel()
        await asyncio.gather(tarefa, return_exceptions=True)


app = FastAPI(title="API Bancaria", lifespan=lifespan)


@app.exception_handler(sqlite3.IntegrityError)
async def erro_integridade(request: Request, exc: sqlite3.IntegrityError):
    mensagens = {
        "SQLITE_CONSTRAINT_UNIQUE": "Ja existe um registro com esses dados unicos",
        "SQLITE_CONSTRAINT_FOREIGNKEY": "Registro possui vinculos e nao pode ser excluido",
    }
    return JSONResponse(status_code=409, content={"detail": mensagens.get(
        exc.sqlite_errorname, "Operacao viola uma restricao do banco")})


def sessao():
    # A manutencao deve persistir mesmo se a operacao solicitada for recusada.
    executar_manutencao()
    with unidade() as db:
        yield db


Db = Annotated[sqlite3.Connection, Depends(sessao, scope="function")]


def salvar(db, tabela, dados, id=None):
    campos = tuple(dados)
    valores = tuple(dados.values())
    if id is None:
        marcadores = ", ".join("?" for _ in campos)
        id = db.execute(
            f"INSERT INTO {tabela} ({', '.join(campos)}) VALUES ({marcadores})", valores
        ).lastrowid
    else:
        atribuicoes = ", ".join(f"{campo} = ?" for campo in campos)
        db.execute(f"UPDATE {tabela} SET {atribuicoes} WHERE id = ?", (*valores, id))
    return publicar(obter(db, tabela, id))


@app.post("/clientes", status_code=201)
def criar_cliente(dados: ClienteDados, db: Db):
    return salvar(db, "clientes", dados.model_dump())


@app.get("/clientes")
def clientes(db: Db):
    return listar(db, "SELECT * FROM clientes ORDER BY id")


@app.get("/clientes/{id}")
def cliente(id: int, db: Db):
    return publicar(obter(db, "clientes", id))


@app.put("/clientes/{id}")
def atualizar_cliente(id: int, dados: ClienteDados, db: Db):
    obter(db, "clientes", id)
    corte = (agora() - timedelta(days=30)).isoformat()
    if dados.situacao == "ativo" and db.execute(
        "SELECT 1 FROM contas WHERE cliente_id = ? AND negativa_desde < ?", (id, corte)
    ).fetchone():
        conflito("Cliente possui conta negativa ha mais de 30 dias")
    return salvar(db, "clientes", dados.model_dump(), id)


@app.delete("/clientes/{id}", status_code=204)
def excluir_cliente(id: int, db: Db):
    obter(db, "clientes", id)
    db.execute("DELETE FROM clientes WHERE id = ?", (id,))
    return Response(status_code=204)


@app.post("/contas", status_code=201)
def criar_conta(dados: ContaNova, db: Db):
    obter(db, "clientes", dados.cliente_id)
    campos = dados.model_dump()
    campos["limite_credito"] = centavos(dados.limite_credito)
    campos["criada_em"] = agora().isoformat()
    return salvar(db, "contas", campos)


@app.get("/contas")
def contas(db: Db, cliente_id: int | None = None):
    return listar(db, "SELECT * FROM contas WHERE (? IS NULL OR cliente_id = ?) ORDER BY id",
                  (cliente_id, cliente_id))


@app.get("/contas/{id}")
def conta(id: int, db: Db):
    return publicar(obter(db, "contas", id))


def encerrar(db, conta):
    if conta["estado"] == "encerrada":
        return
    if conta["saldo"] != 0:
        conflito("O encerramento exige saldo zero")
    id = conta["id"]
    if db.execute("""
        SELECT 1 FROM faturas f JOIN cartoes c ON c.id = f.cartao_id
        WHERE c.conta_id = ? AND f.estado != 'paga'
    """, (id,)).fetchone():
        conflito("A conta possui fatura em aberto")
    db.execute("UPDATE cartoes SET estado = 'cancelado' WHERE conta_id = ?", (id,))
    db.execute("UPDATE contas SET estado = 'encerrada' WHERE id = ?", (id,))


@app.put("/contas/{id}")
def atualizar_conta(id: int, dados: ContaDados, db: Db):
    atual = obter(db, "contas", id)
    if atual["estado"] == "encerrada":
        conflito("Conta encerrada")
    campos = dados.model_dump()
    campos["limite_credito"] = centavos(dados.limite_credito)
    if atual["saldo"] < -campos["limite_credito"]:
        conflito("O saldo atual excede o novo limite de credito")
    if dados.estado == "encerrada":
        encerrar(db, atual)
    return salvar(db, "contas", campos, id)


@app.delete("/contas/{id}", status_code=204)
def excluir_conta(id: int, db: Db):
    encerrar(db, obter(db, "contas", id))
    return Response(status_code=204)


@app.post("/cartoes", status_code=201)
def criar_cartao(dados: CartaoNovo, db: Db):
    conta = obter(db, "contas", dados.conta_id)
    exigir_ativa(conta, obter(db, "clientes", conta["cliente_id"]))
    campos = dados.model_dump()
    campos["limite"] = centavos(dados.limite)
    return salvar(db, "cartoes", campos)


@app.get("/cartoes")
def cartoes(db: Db, conta_id: int | None = None):
    return listar(db, "SELECT * FROM cartoes WHERE (? IS NULL OR conta_id = ?) ORDER BY id",
                  (conta_id, conta_id))


@app.get("/cartoes/{id}")
def cartao(id: int, db: Db):
    return publicar(obter(db, "cartoes", id))


@app.put("/cartoes/{id}")
def atualizar_cartao(id: int, dados: CartaoDados, db: Db):
    atual = obter(db, "cartoes", id)
    if atual["estado"] == "cancelado":
        conflito("Cartao cancelado")
    if dados.estado == "ativo":
        conta = obter(db, "contas", atual["conta_id"])
        exigir_ativa(conta, obter(db, "clientes", conta["cliente_id"]))
        corte = (agora().date() - timedelta(days=10)).isoformat()
        if db.execute("""
            SELECT 1 FROM faturas WHERE cartao_id = ? AND estado = 'atrasada' AND vencimento <= ?
        """, (id, corte)).fetchone():
            conflito("Cartao bloqueado por atraso de fatura")
    campos = dados.model_dump()
    campos["limite"] = centavos(dados.limite)
    return salvar(db, "cartoes", campos, id)


@app.delete("/cartoes/{id}", status_code=204)
def excluir_cartao(id: int, db: Db):
    obter(db, "cartoes", id)
    db.execute("UPDATE cartoes SET estado = 'cancelado' WHERE id = ?", (id,))
    return Response(status_code=204)


@app.post("/transacoes/deposito", status_code=201)
def deposito(dados: Movimento, db: Db):
    return movimentar(db, "deposito", dados, agora())


@app.post("/transacoes/saque", status_code=201)
def saque(dados: Movimento, db: Db):
    return movimentar(db, "saque", dados, agora())


@app.post("/transacoes/transferencia", status_code=201)
def transferencia(dados: Transferencia, db: Db):
    return movimentar(db, "transferencia", dados, agora())


@app.post("/transacoes/{id}/estorno", status_code=201)
def estorno(id: int, db: Db):
    return estornar(db, id, agora())


@app.get("/contas/{id}/extrato")
def extrato(id: int, db: Db):
    obter(db, "contas", id)
    return listar(db, """
        SELECT * FROM transacoes WHERE conta_id = ? OR destino_id = ? ORDER BY data, id
    """, (id, id))


@app.get("/contas/{id}/tarifas")
def tarifas(id: int, db: Db):
    obter(db, "contas", id)
    return listar(db, "SELECT * FROM tarifas WHERE conta_id = ? ORDER BY id", (id,))


@app.post("/cartoes/{id}/faturas", status_code=201)
def criar_fatura(id: int, dados: FaturaNova, db: Db):
    cartao = obter(db, "cartoes", id)
    if cartao["estado"] == "cancelado":
        conflito("Cartao cancelado")
    valor = centavos(dados.valor)
    fatura = salvar(db, "faturas", {
        "cartao_id": id, "mes_referencia": dados.mes_referencia,
        "vencimento": dados.vencimento.isoformat(), "valor_base": valor,
        "valor": valor, "estado": dados.estado,
    })
    manutencao(db, agora())
    return publicar(obter(db, "faturas", fatura["id"]))


@app.get("/cartoes/{id}/faturas")
def faturas(id: int, db: Db):
    obter(db, "cartoes", id)
    return listar(db, "SELECT * FROM faturas WHERE cartao_id = ? ORDER BY mes_referencia", (id,))


@app.post("/faturas/{id}/pagamento")
def pagamento(id: int, db: Db):
    fatura = obter(db, "faturas", id)
    if fatura["estado"] == "paga":
        conflito("Fatura ja paga")
    cartao = obter(db, "cartoes", fatura["cartao_id"])
    instante = agora()
    saldo(db, cartao["conta_id"], -fatura["valor"], instante)
    return salvar(db, "faturas", {"estado": "paga", "paga_em": instante.isoformat()}, id)


@app.get("/relatorios/clientes-maior-movimentacao")
def maior_movimentacao(db: Db, inicio: date, fim: date,
                       limite: Annotated[int, Query(ge=1, le=100)] = 10):
    if inicio > fim:
        raise HTTPException(422, "Inicio deve ser anterior ou igual ao fim")
    linhas = db.execute("""
        WITH movimentos AS (
            SELECT a.cliente_id AS origem, b.cliente_id AS destino, t.valor
            FROM transacoes t JOIN contas a ON a.id = t.conta_id
            LEFT JOIN contas b ON b.id = t.destino_id
            WHERE t.estado = 'efetivada' AND t.tipo != 'estorno'
            AND substr(t.data, 1, 10) BETWEEN ? AND ?
        ), valores AS (
            SELECT origem AS cliente_id, valor FROM movimentos
            UNION ALL
            SELECT destino, valor FROM movimentos WHERE destino != origem
        )
        SELECT c.id AS cliente_id, c.nome, SUM(v.valor) AS movimentacao
        FROM valores v JOIN clientes c ON c.id = v.cliente_id
        GROUP BY c.id ORDER BY movimentacao DESC, c.id LIMIT ?
    """, (inicio.isoformat(), fim.isoformat(), limite))
    return [dict(linha, movimentacao=reais(linha["movimentacao"])) for linha in linhas]


@app.get("/relatorios/contas-saldo-negativo")
def contas_negativas(db: Db):
    return listar(db, "SELECT * FROM contas WHERE saldo < 0 ORDER BY saldo, id")


@app.get("/relatorios/receita-tarifas")
def receita_tarifas(db: Db, inicio: date | None = None, fim: date | None = None):
    if inicio and fim and inicio > fim:
        raise HTTPException(422, "Inicio deve ser anterior ou igual ao fim")
    de = (inicio or date.min).isoformat()
    ate = (fim or date.max).isoformat()
    totais = dict(db.execute("""
        SELECT categoria, SUM(valor) FROM tarifas WHERE estado = 'cobrada'
        AND substr(cobrada_em, 1, 10) BETWEEN ? AND ? GROUP BY categoria
    """, (de, ate)).fetchall())
    return [{"categoria": categoria, "receita": reais(totais.get(categoria, 0))}
            for categoria in ("comum", "premium", "empresarial")]
