import asyncio
import logging
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, Response
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from banco import (RULES, TRANSFER_FEE, agora, alterar_saldo, atualizar_pendencias,
                   banco, centavos, iniciar)

Categoria = Literal["comum", "premium", "empresarial"]
Situacao = Literal["ativo", "bloqueado"]
TipoConta = Literal["corrente", "poupanca"]
EstadoConta = Literal["ativa", "bloqueada", "encerrada"]
EstadoCartao = Literal["ativo", "bloqueado", "cancelado"]
Id = Annotated[int, Path(gt=0, le=2**63 - 1)]
IdEntrada = Annotated[int, Field(gt=0, le=2**63 - 1)]
Dinheiro = Annotated[Decimal, Field(ge=0, le=10**12, decimal_places=2)]
Valor = Annotated[Decimal, Field(gt=0, le=10**12, decimal_places=2)]
Nome = Annotated[str, Field(min_length=1, max_length=150)]
Numero = Annotated[str, Field(pattern=r"^[0-9]{1,24}$")]
Email = Annotated[str, Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]


def normalizar_cpf(cpf):
    cpf = re.sub(r"[.-]", "", cpf)
    if len(set(cpf)) == 1:
        raise ValueError("CPF invalido")
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        if int(cpf[tamanho]) != (soma * 10 % 11) % 10:
            raise ValueError("CPF invalido")
    return cpf


CPF = Annotated[str, Field(pattern=r"^(?:[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2})$"),
                AfterValidator(normalizar_cpf)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Cliente(Entrada):
    nome: Nome
    cpf: CPF
    email: Email
    categoria: Categoria
    situacao: Situacao = "ativo"


class Conta(Entrada):
    cliente_id: IdEntrada
    numero: Numero
    tipo: TipoConta
    limite_credito: Dinheiro = Decimal(0)


class AtualizarConta(Entrada):
    numero: Numero
    tipo: TipoConta
    limite_credito: Dinheiro
    estado: EstadoConta


class Cartao(Entrada):
    conta_id: IdEntrada
    numero: Numero
    limite: Dinheiro


class AtualizarCartao(Entrada):
    numero: Numero
    limite: Dinheiro
    estado: EstadoCartao


class Movimento(Entrada):
    valor: Valor


class Transferencia(Movimento):
    destino_id: IdEntrada


class NovaFatura(Movimento):
    mes_referencia: Annotated[str, Field(pattern=r"^[1-9][0-9]{3}-(0[1-9]|1[0-2])$")]
    vencimento: date
    estado: Literal["aberta", "fechada"] = "fechada"


def manutencao():
    with banco() as db:
        atualizar_pendencias(db, agora())


async def manutencao_periodica():
    while True:
        try:
            await asyncio.to_thread(manutencao)
        except Exception:
            logging.exception("Falha na manutencao bancaria")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(iniciar)
    await asyncio.to_thread(manutencao)
    tarefa = asyncio.create_task(manutencao_periodica())
    try:
        yield
    finally:
        tarefa.cancel()
        await asyncio.gather(tarefa, return_exceptions=True)


app = FastAPI(title="API de Contas Bancarias", lifespan=lifespan)


@app.middleware("http")
async def sincronizar_estados(request, call_next):
    if request.url.path not in ("/docs", "/redoc", "/openapi.json"):
        await asyncio.to_thread(manutencao)
    return await call_next(request)


@app.exception_handler(sqlite3.IntegrityError)
async def conflito_integridade(request, exc):
    return JSONResponse(status_code=409, content={"detail": "Registro duplicado ou vinculado."})


def conflito(mensagem):
    raise HTTPException(409, mensagem)


def obter(db, tabela, id):
    item = db.execute(f"SELECT * FROM {tabela} WHERE id=?", (id,)).fetchone()
    if item is None:
        raise HTTPException(404, "Registro nao encontrado.")
    return item


def mostrar(registro):
    item = dict(registro)
    for campo in ("saldo", "limite_credito", "limite", "valor", "principal", "movimentacao", "receita"):
        if campo in item:
            item[campo] = f"{Decimal(item[campo]) / 100:.2f}"
    return item


def lista(registros):
    return [mostrar(registro) for registro in registros]


@app.post("/clientes", status_code=201)
def criar_cliente(dados: Cliente):
    with banco() as db:
        id = db.execute("INSERT INTO clientes(nome,cpf,email,categoria,situacao) VALUES (?,?,?,?,?)",
                        tuple(dados.model_dump().values())).lastrowid
        return mostrar(obter(db, "clientes", id))


@app.get("/clientes")
def listar_clientes():
    with banco() as db:
        return lista(db.execute("SELECT * FROM clientes ORDER BY id"))


@app.get("/clientes/{id}")
def consultar_cliente(id: Id):
    with banco() as db:
        return mostrar(obter(db, "clientes", id))


@app.put("/clientes/{id}")
def atualizar_cliente(id: Id, dados: Cliente):
    with banco() as db:
        obter(db, "clientes", id)
        momento = agora()
        db.execute("UPDATE clientes SET nome=?,cpf=?,email=?,categoria=?,situacao=? WHERE id=?",
                   (*dados.model_dump().values(), id))
        atualizar_pendencias(db, momento)
        return mostrar(obter(db, "clientes", id))


@app.delete("/clientes/{id}", status_code=204)
def excluir_cliente(id: Id):
    with banco() as db:
        obter(db, "clientes", id)
        db.execute("DELETE FROM clientes WHERE id=?", (id,))
    return Response(status_code=204)


@app.post("/contas", status_code=201)
def criar_conta(dados: Conta):
    with banco() as db:
        obter(db, "clientes", dados.cliente_id)
        id = db.execute("""INSERT INTO contas(cliente_id,numero,tipo,limite_credito,criada_em)
                           VALUES (?,?,?,?,?)""",
                        (dados.cliente_id, dados.numero, dados.tipo,
                         centavos(dados.limite_credito), agora().isoformat())).lastrowid
        return mostrar(obter(db, "contas", id))


@app.get("/contas")
def listar_contas():
    with banco() as db:
        return lista(db.execute("SELECT * FROM contas ORDER BY id"))


@app.get("/contas/{id}")
def consultar_conta(id: Id):
    with banco() as db:
        return mostrar(obter(db, "contas", id))


def encerrar(db, conta):
    if conta["saldo"] or db.execute("""
        SELECT 1 FROM faturas f JOIN cartoes k ON k.id=f.cartao_id
        WHERE k.conta_id=? AND f.estado != 'paga'
    """, (conta["id"],)).fetchone():
        conflito("O encerramento exige saldo zero e nenhuma fatura em aberto.")
    db.execute("UPDATE contas SET estado='encerrada' WHERE id=?", (conta["id"],))
    db.execute("UPDATE cartoes SET estado='cancelado' WHERE conta_id=?", (conta["id"],))


@app.put("/contas/{id}")
def atualizar_conta(id: Id, dados: AtualizarConta):
    with banco() as db:
        conta = obter(db, "contas", id)
        if conta["estado"] == "encerrada":
            conflito("Conta encerrada.")
        limite = centavos(dados.limite_credito)
        if conta["saldo"] < -limite:
            conflito("O novo limite deve cobrir o saldo devedor.")
        if dados.estado == "encerrada":
            encerrar(db, conta)
        db.execute("UPDATE contas SET numero=?,tipo=?,limite_credito=?,estado=? WHERE id=?",
                   (dados.numero, dados.tipo, limite, dados.estado, id))
        return mostrar(obter(db, "contas", id))


@app.delete("/contas/{id}", status_code=204)
def excluir_conta(id: Id):
    with banco() as db:
        encerrar(db, obter(db, "contas", id))
    return Response(status_code=204)


@app.post("/cartoes", status_code=201)
def criar_cartao(dados: Cartao):
    with banco() as db:
        conta = obter(db, "contas", dados.conta_id)
        cliente_ativo(db, conta)
        id = db.execute("INSERT INTO cartoes(conta_id,numero,limite) VALUES (?,?,?)",
                        (dados.conta_id, dados.numero, centavos(dados.limite))).lastrowid
        return mostrar(obter(db, "cartoes", id))


@app.get("/cartoes")
def listar_cartoes():
    with banco() as db:
        return lista(db.execute("SELECT * FROM cartoes ORDER BY id"))


@app.get("/cartoes/{id}")
def consultar_cartao(id: Id):
    with banco() as db:
        return mostrar(obter(db, "cartoes", id))


@app.put("/cartoes/{id}")
def atualizar_cartao(id: Id, dados: AtualizarCartao):
    with banco() as db:
        cartao = obter(db, "cartoes", id)
        if cartao["estado"] == "cancelado":
            conflito("Cartao cancelado.")
        if dados.estado == "ativo":
            cliente_ativo(db, obter(db, "contas", cartao["conta_id"]))
            limite_atraso = (agora().date() - timedelta(days=10)).isoformat()
            if db.execute("""SELECT 1 FROM faturas WHERE cartao_id=?
                             AND estado='atrasada' AND vencimento<=?""", (id, limite_atraso)).fetchone():
                conflito("Cartao com fatura em atraso ha pelo menos 10 dias.")
        db.execute("UPDATE cartoes SET numero=?,limite=?,estado=? WHERE id=?",
                   (dados.numero, centavos(dados.limite), dados.estado, id))
        return mostrar(obter(db, "cartoes", id))


@app.delete("/cartoes/{id}", status_code=204)
def excluir_cartao(id: Id):
    with banco() as db:
        obter(db, "cartoes", id)
        db.execute("UPDATE cartoes SET estado='cancelado' WHERE id=?", (id,))
    return Response(status_code=204)


def cliente_ativo(db, conta):
    cliente = obter(db, "clientes", conta["cliente_id"])
    if conta["estado"] != "ativa" or cliente["situacao"] != "ativo":
        conflito("A operacao exige conta e cliente ativos.")
    return cliente


def creditar_ou_debitar(db, conta, delta, momento):
    if conta["estado"] == "encerrada":
        conflito("Conta encerrada.")
    if conta["saldo"] + delta < -conta["limite_credito"]:
        conflito("Saldo e limite de credito insuficientes.")
    alterar_saldo(db, conta, delta, momento)


def mostrar_transacao(db, transacao_id):
    item = mostrar(obter(db, "transacoes", transacao_id))
    item["lancamentos"] = lista(db.execute("""
        SELECT conta_id, valor FROM lancamentos WHERE transacao_id=? ORDER BY valor
    """, (transacao_id,)))
    return item


def registrar(db, tipo, valor, momento, lancamentos, original_id=None):
    id = db.execute("INSERT INTO transacoes(tipo,valor,data,original_id) VALUES (?,?,?,?)",
                    (tipo, valor, momento.isoformat(), original_id)).lastrowid
    for conta, delta in lancamentos:
        creditar_ou_debitar(db, conta, delta, momento)
        db.execute("INSERT INTO lancamentos VALUES (?,?,?)", (id, conta["id"], delta))
    return id


@app.post("/contas/{id}/depositos", status_code=201)
def deposito(id: Id, dados: Movimento):
    with banco() as db:
        momento = agora()
        conta = obter(db, "contas", id)
        valor = centavos(dados.valor)
        return mostrar_transacao(db, registrar(db, "deposito", valor, momento, [(conta, valor)]))


@app.post("/contas/{id}/saques", status_code=201)
def saque(id: Id, dados: Movimento):
    with banco() as db:
        momento = agora()
        conta = obter(db, "contas", id)
        cliente = cliente_ativo(db, conta)
        valor = centavos(dados.valor)
        utilizado = db.execute("""
            SELECT COALESCE(SUM(t.valor),0) FROM transacoes t
            JOIN lancamentos l ON l.transacao_id=t.id JOIN contas c ON c.id=l.conta_id
            WHERE c.cliente_id=? AND t.tipo='saque' AND t.estado='efetivada' AND t.data>=?
        """, (cliente["id"], momento.date().isoformat())).fetchone()[0]
        if utilizado + valor > RULES[cliente["categoria"]][0]:
            conflito("Limite diario de saque excedido.")
        return mostrar_transacao(db, registrar(db, "saque", valor, momento, [(conta, -valor)]))


@app.post("/contas/{id}/transferencias", status_code=201)
def transferencia(id: Id, dados: Transferencia):
    if id == dados.destino_id:
        raise HTTPException(422, "As contas de origem e destino devem ser diferentes.")
    with banco() as db:
        momento = agora()
        origem = obter(db, "contas", id)
        destino = obter(db, "contas", dados.destino_id)
        cliente = cliente_ativo(db, origem)
        valor = centavos(dados.valor)
        _, limite, _, franquia, _ = RULES[cliente["categoria"]]
        if valor > limite:
            conflito("Limite por transferencia excedido.")
        transacao = registrar(db, "transferencia", valor, momento,
                              [(origem, -valor), (destino, valor)])
        referencia = momento.strftime("%Y-%m")
        tarifa = 0
        if origem["cliente_id"] != destino["cliente_id"] and franquia is not None:
            utilizadas = db.execute("""
                SELECT COUNT(*) FROM tarifas t JOIN contas c ON c.id=t.conta_id
                JOIN transacoes m ON m.id=t.transacao_id
                WHERE c.cliente_id=? AND t.tipo='transferencia' AND t.referencia=?
                  AND m.estado='efetivada'
            """, (cliente["id"], referencia)).fetchone()[0]
            if utilizadas >= franquia:
                tarifa = centavos(TRANSFER_FEE)
        if origem["cliente_id"] != destino["cliente_id"]:
            if tarifa:
                creditar_ou_debitar(db, obter(db, "contas", id), -tarifa, momento)
            db.execute("""INSERT INTO tarifas(conta_id,tipo,valor,estado,categoria,referencia,
                                              transacao_id,cobrada_em)
                          VALUES (?,'transferencia',?,?,?,?,?,?)""",
                       (id, tarifa, "cobrada" if tarifa else "isenta", cliente["categoria"],
                        referencia, transacao, momento.isoformat() if tarifa else None))
        return mostrar_transacao(db, transacao)


@app.post("/transacoes/{id}/estornos", status_code=201)
def estorno(id: Id):
    with banco() as db:
        momento = agora()
        original = obter(db, "transacoes", id)
        if (original["tipo"] == "estorno" or original["estado"] != "efetivada"
                or momento - datetime.fromisoformat(original["data"]) > timedelta(hours=24)):
            conflito("A transacao nao pode ser estornada.")
        lancamentos = [(obter(db, "contas", linha["conta_id"]), -linha["valor"])
                       for linha in db.execute("SELECT * FROM lancamentos WHERE transacao_id=?", (id,))]
        reversao = registrar(db, "estorno", original["valor"], momento, lancamentos, id)
        tarifa = db.execute("""
            SELECT * FROM tarifas WHERE transacao_id=? AND estado='cobrada'
        """, (id,)).fetchone()
        if tarifa:
            conta = obter(db, "contas", tarifa["conta_id"])
            creditar_ou_debitar(db, conta, tarifa["valor"], momento)
            db.execute("UPDATE tarifas SET estado='isenta', valor=0, cobrada_em=NULL WHERE id=?",
                       (tarifa["id"],))
        db.execute("UPDATE transacoes SET estado='estornada' WHERE id=?", (id,))
        return mostrar_transacao(db, reversao)


@app.get("/contas/{id}/extrato")
def extrato(id: Id):
    with banco() as db:
        obter(db, "contas", id)
        return lista(db.execute("""
            SELECT t.id, t.tipo, t.data, t.estado, t.original_id, l.valor
            FROM lancamentos l JOIN transacoes t ON t.id=l.transacao_id
            WHERE l.conta_id=? ORDER BY t.data DESC, t.id DESC
        """, (id,)))


@app.post("/cartoes/{id}/faturas", status_code=201)
def criar_fatura(id: Id, dados: NovaFatura):
    with banco() as db:
        cartao = obter(db, "cartoes", id)
        if cartao["estado"] != "ativo":
            conflito("A emissao exige cartao ativo.")
        valor = centavos(dados.valor)
        fatura = db.execute("""
            INSERT INTO faturas(cartao_id,mes_referencia,principal,valor,vencimento,estado)
            VALUES (?,?,?,?,?,?)
        """, (id, dados.mes_referencia, valor, valor, dados.vencimento.isoformat(), dados.estado)).lastrowid
        atualizar_pendencias(db, agora())
        return mostrar(obter(db, "faturas", fatura))


@app.get("/cartoes/{id}/faturas")
def listar_faturas(id: Id):
    with banco() as db:
        obter(db, "cartoes", id)
        return lista(db.execute("SELECT * FROM faturas WHERE cartao_id=? ORDER BY mes_referencia DESC", (id,)))


@app.post("/faturas/{id}/fechamento")
def fechar_fatura(id: Id):
    with banco() as db:
        fatura = obter(db, "faturas", id)
        if fatura["estado"] != "aberta":
            conflito("O fechamento exige fatura aberta.")
        db.execute("UPDATE faturas SET estado='fechada' WHERE id=?", (id,))
        return mostrar(obter(db, "faturas", id))


@app.post("/faturas/{id}/pagamento")
def pagar_fatura(id: Id):
    with banco() as db:
        momento = agora()
        fatura = obter(db, "faturas", id)
        if fatura["estado"] not in ("fechada", "atrasada"):
            conflito("O pagamento exige fatura fechada ou atrasada.")
        cartao = obter(db, "cartoes", fatura["cartao_id"])
        conta = obter(db, "contas", cartao["conta_id"])
        creditar_ou_debitar(db, conta, -fatura["valor"], momento)
        db.execute("UPDATE faturas SET estado='paga', paga_em=? WHERE id=?",
                   (momento.isoformat(), id))
        return mostrar(obter(db, "faturas", id))


@app.get("/contas/{id}/tarifas")
def listar_tarifas(id: Id):
    with banco() as db:
        obter(db, "contas", id)
        return lista(db.execute("SELECT * FROM tarifas WHERE conta_id=? ORDER BY id DESC", (id,)))


def periodo(inicio, fim):
    if inicio > fim:
        raise HTTPException(422, "A data inicial deve ser anterior ou igual a data final.")
    return inicio.isoformat(), fim.isoformat()


@app.get("/relatorios/clientes-maior-movimentacao")
def maior_movimentacao(inicio: date, fim: date):
    with banco() as db:
        return lista(db.execute("""
            WITH por_transacao AS (
                SELECT c.cliente_id, t.id, MAX(ABS(l.valor)) AS valor
                FROM lancamentos l JOIN transacoes t ON t.id=l.transacao_id
                JOIN contas c ON c.id=l.conta_id
                WHERE t.estado='efetivada' AND t.tipo!='estorno'
                  AND substr(t.data,1,10) BETWEEN ? AND ?
                GROUP BY c.cliente_id, t.id
            )
            SELECT p.id AS cliente_id, p.nome, SUM(m.valor) AS movimentacao
            FROM por_transacao m JOIN clientes p ON p.id=m.cliente_id
            GROUP BY p.id ORDER BY movimentacao DESC, p.id
        """, periodo(inicio, fim)))


@app.get("/relatorios/contas-saldo-negativo")
def contas_negativas():
    with banco() as db:
        return lista(db.execute("SELECT * FROM contas WHERE saldo<0 ORDER BY saldo, id"))


@app.get("/relatorios/receita-tarifas")
def receita_tarifas(inicio: date, fim: date):
    with banco() as db:
        receitas = dict(db.execute("""
            SELECT categoria, SUM(valor) FROM tarifas WHERE estado='cobrada'
              AND substr(cobrada_em,1,10) BETWEEN ? AND ? GROUP BY categoria
        """, periodo(inicio, fim)).fetchall())
        return [mostrar({"categoria": categoria, "receita": receitas.get(categoria, 0)})
                for categoria in RULES]

