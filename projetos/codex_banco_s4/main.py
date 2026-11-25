import asyncio
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from logging import getLogger
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse

from modelos import Cartao, CartaoDados, Cliente, Conta, ContaDados, Fatura, Movimento, Transferencia

# Saque diario, transferencia, mensalidade (centavos), franquia, juros (%).
REGRAS = {
    "comum": (100_000, 500_000, 3000, 3, 8),
    "premium": (500_000, 5_000_000, 0, None, 5),
    "empresarial": (2_000_000, 20_000_000, 12000, 50, 3),
}
FUSO_BANCARIO = timezone(timedelta(hours=-3))
CAMPOS_MONETARIOS = {"valor", "saldo", "limite", "limite_credito", "juros", "total"}
logger = getLogger(__name__)


def agora():
    return datetime.now(UTC)


def centavos(valor):
    return int(valor * 100)


def apresentar(linha):
    return {
        chave: format(Decimal(valor).scaleb(-2), ".2f")
        if chave in CAMPOS_MONETARIOS else valor
        for chave, valor in dict(linha).items()
        if chave not in {"dia", "usa_franquia", "taxa_atraso", "aberta_em"}
    }


def buscar(db, tabela, identificador):
    linha = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (identificador,)).fetchone()
    if linha is None:
        raise HTTPException(404, "Registro inexistente")
    return linha


def listar(db, sql, parametros=()):
    return [apresentar(linha) for linha in db.execute(sql, parametros)]


def inserir(db, tabela, **dados):
    colunas = ", ".join(dados)
    marcadores = ", ".join("?" for _ in dados)
    cursor = db.execute(
        f"INSERT INTO {tabela} ({colunas}) VALUES ({marcadores})", tuple(dados.values())
    )
    return cursor.lastrowid


def atualizar(db, tabela, identificador, **dados):
    campos = ", ".join(f"{chave} = ?" for chave in dados)
    db.execute(f"UPDATE {tabela} SET {campos} WHERE id = ?", (*dados.values(), identificador))


def saldo(db, conta, diferenca, agora_em):
    novo = conta["saldo"] + diferenca
    if novo < -conta["limite_credito"]:
        raise HTTPException(409, "Saldo e limite de credito insuficientes")
    desde = (conta["negativo_desde"] or agora_em.isoformat()) if novo < 0 else None
    atualizar(db, "contas", conta["id"], saldo=novo, negativo_desde=desde)


def validar_conta(db, conta):
    cliente = buscar(db, "clientes", conta["cliente_id"])
    if conta["estado"] != "ativa" or cliente["situacao"] != "ativo":
        raise HTTPException(409, "Conta ou cliente indisponivel para a operacao")
    return cliente


def calendario(db, instante):
    hoje = instante.astimezone(FUSO_BANCARIO).date()
    competencia = hoje.strftime("%Y-%m")
    clientes_em_atraso = """
        SELECT cliente_id FROM contas WHERE negativo_desde < ?
    """
    corte = (instante - timedelta(days=30)).isoformat()
    db.execute(
        f"UPDATE clientes SET situacao = 'bloqueado' WHERE id IN ({clientes_em_atraso})", (corte,)
    )
    db.execute(
        f"""UPDATE cartoes SET estado = 'bloqueado' WHERE estado = 'ativo'
        AND conta_id IN (SELECT id FROM contas WHERE cliente_id IN ({clientes_em_atraso}))""",
        (corte,),
    )
    faturas = db.execute("""
        SELECT f.*, c.categoria FROM faturas f JOIN cartoes ca ON ca.id = f.cartao_id
        JOIN contas co ON co.id = ca.conta_id JOIN clientes c ON c.id = co.cliente_id
        WHERE f.estado <> 'paga' AND f.vencimento < ?
    """, (hoje.isoformat(),)).fetchall()
    for fatura in faturas:
        dias = (hoje - date.fromisoformat(fatura["vencimento"])).days
        taxa = fatura["taxa_atraso"] or REGRAS[fatura["categoria"]][4]
        juros = int((Decimal(fatura["valor"] * taxa * dias) / 3000).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ))
        atualizar(db, "faturas", fatura["id"], estado="atrasada", juros=juros, taxa_atraso=taxa)
        if dias > 10:
            db.execute("UPDATE cartoes SET estado = 'bloqueado' WHERE id = ? AND estado = 'ativo'",
                       (fatura["cartao_id"],))

    competencias = db.execute("""
        WITH RECURSIVE meses(id, categoria, mes) AS (
            SELECT co.id, c.categoria, substr(co.aberta_em, 1, 7) FROM contas co
            JOIN clientes c ON c.id = co.cliente_id WHERE co.estado <> 'encerrada'
            UNION ALL
            SELECT id, categoria, strftime('%Y-%m', date(mes || '-01', '+1 month'))
            FROM meses WHERE mes < ?
        )
        SELECT m.* FROM meses m WHERE m.mes <= ? AND NOT EXISTS (
            SELECT 1 FROM tarifas t WHERE t.conta_id = m.id AND t.tipo = 'mensal'
            AND t.competencia = m.mes
        ) ORDER BY m.mes, m.id
    """, (competencia, competencia)).fetchall()
    for conta in competencias:
        mensal = REGRAS[conta["categoria"]][2]
        inserir(db, "tarifas", conta_id=conta["id"], tipo="mensal", valor=mensal,
                estado="pendente" if mensal else "isenta", competencia=conta["mes"],
                categoria=conta["categoria"])

    pendentes = db.execute("""
        SELECT t.* FROM tarifas t JOIN contas co ON co.id = t.conta_id
        WHERE t.estado = 'pendente' AND co.estado <> 'encerrada' ORDER BY t.id
    """).fetchall()
    for tarifa in pendentes:
        cobrar(db, tarifa, instante)


def cobrar(db, tarifa, instante):
    conta = buscar(db, "contas", tarifa["conta_id"])
    if conta["saldo"] + conta["limite_credito"] >= tarifa["valor"]:
        saldo(db, conta, -tarifa["valor"], instante)
        atualizar(db, "tarifas", tarifa["id"], estado="cobrada", cobrada_em=instante.isoformat())


def criar_app(caminho=None, tarifa_excedente=Decimal("1.00")):
    caminho = caminho or os.getenv("BANCO_DB", "banco.sqlite3")
    if (not tarifa_excedente.is_finite() or tarifa_excedente <= 0
            or tarifa_excedente != tarifa_excedente.quantize(Decimal("0.01"))):
        raise ValueError("A tarifa excedente deve ser positiva e expressa em centavos inteiros")

    @contextmanager
    def sessao():
        db = sqlite3.connect(caminho, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def manutencao():
        with sessao() as db:
            calendario(db, agora())

    async def periodico():
        while True:
            await asyncio.sleep(60)
            try:
                await asyncio.to_thread(manutencao)
            except sqlite3.Error:
                logger.exception("Falha na atualizacao periodica do banco")

    @asynccontextmanager
    async def lifespan(app):
        with sessao() as db:
            db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        manutencao()
        tarefa = asyncio.create_task(periodico())
        try:
            yield
        finally:
            tarefa.cancel()
            await asyncio.gather(tarefa, return_exceptions=True)

    app = FastAPI(title="API bancaria", lifespan=lifespan)

    @app.exception_handler(sqlite3.IntegrityError)
    async def conflito(_, exc):
        return JSONResponse(status_code=409, content={"detail": "Registro duplicado ou vinculado"})

    @contextmanager
    def operacao():
        erro = None
        with sessao() as db:
            instante = agora()
            calendario(db, instante)
            # Uma operacao negada preserva apenas as mudancas da manutencao.
            db.execute("SAVEPOINT operacao")
            try:
                yield db, instante
            except (HTTPException, sqlite3.IntegrityError) as exc:
                db.execute("ROLLBACK TO operacao")
                erro = exc
            db.execute("RELEASE operacao")
        if erro is not None:
            raise erro

    def ler(tabela, identificador):
        with operacao() as (db, _):
            return apresentar(buscar(db, tabela, identificador))

    def colecao(tabela):
        with operacao() as (db, _):
            return listar(db, f"SELECT * FROM {tabela} ORDER BY id")

    @app.post("/clientes", status_code=201)
    def criar_cliente(dados: Cliente):
        with operacao() as (db, _):
            identificador = inserir(db, "clientes", **dados.model_dump())
            return apresentar(buscar(db, "clientes", identificador))

    @app.get("/clientes")
    def clientes():
        return colecao("clientes")

    @app.get("/clientes/{cliente_id}")
    def cliente(cliente_id: int):
        return ler("clientes", cliente_id)

    @app.put("/clientes/{cliente_id}")
    def editar_cliente(cliente_id: int, dados: Cliente):
        with operacao() as (db, instante):
            buscar(db, "clientes", cliente_id)
            atualizar(db, "clientes", cliente_id, **dados.model_dump())
            if dados.situacao == "bloqueado":
                db.execute("""UPDATE cartoes SET estado = 'bloqueado' WHERE estado = 'ativo'
                    AND conta_id IN (SELECT id FROM contas WHERE cliente_id = ?)""", (cliente_id,))
            calendario(db, instante)
            return apresentar(buscar(db, "clientes", cliente_id))

    @app.delete("/clientes/{cliente_id}", status_code=204)
    def excluir_cliente(cliente_id: int):
        with operacao() as (db, _):
            buscar(db, "clientes", cliente_id)
            db.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
        return Response(status_code=204)

    @app.post("/contas", status_code=201)
    def criar_conta(dados: Conta):
        with operacao() as (db, instante):
            buscar(db, "clientes", dados.cliente_id)
            if dados.estado == "encerrada":
                raise HTTPException(409, "Conta nova deve estar ativa ou bloqueada")
            campos = dados.model_dump()
            campos["limite_credito"] = centavos(dados.limite_credito)
            identificador = inserir(db, "contas", **campos,
                                    aberta_em=instante.astimezone(FUSO_BANCARIO).date().isoformat())
            return apresentar(buscar(db, "contas", identificador))

    @app.get("/contas")
    def contas():
        return colecao("contas")

    @app.get("/contas/{conta_id}")
    def conta(conta_id: int):
        return ler("contas", conta_id)

    def encerrar(db, conta):
        pendencia = db.execute("""
            SELECT 1 FROM faturas f JOIN cartoes c ON c.id = f.cartao_id
            WHERE c.conta_id = ? AND f.estado <> 'paga' LIMIT 1
        """, (conta["id"],)).fetchone()
        if conta["saldo"] != 0 or pendencia:
            raise HTTPException(409, "Encerramento exige saldo zero e faturas quitadas")
        atualizar(db, "contas", conta["id"], estado="encerrada")
        db.execute("UPDATE cartoes SET estado = 'cancelado' WHERE conta_id = ?", (conta["id"],))

    @app.put("/contas/{conta_id}")
    def editar_conta(conta_id: int, dados: ContaDados):
        with operacao() as (db, _):
            registro = buscar(db, "contas", conta_id)
            if registro["estado"] == "encerrada":
                raise HTTPException(409, "Conta encerrada")
            limite = centavos(dados.limite_credito)
            if registro["saldo"] < -limite:
                raise HTTPException(409, "Limite inferior ao credito utilizado")
            if dados.estado == "encerrada":
                encerrar(db, registro)
            atualizar(db, "contas", conta_id, tipo=dados.tipo, limite_credito=limite,
                      estado=dados.estado)
            return apresentar(buscar(db, "contas", conta_id))

    @app.delete("/contas/{conta_id}", status_code=204)
    def excluir_conta(conta_id: int):
        with operacao() as (db, _):
            encerrar(db, buscar(db, "contas", conta_id))
        return Response(status_code=204)

    @app.post("/cartoes", status_code=201)
    def criar_cartao(dados: Cartao):
        with operacao() as (db, _):
            conta = buscar(db, "contas", dados.conta_id)
            validar_conta(db, conta)
            if dados.estado == "cancelado":
                raise HTTPException(409, "Cartao novo deve estar ativo ou bloqueado")
            campos = dados.model_dump()
            campos["limite"] = centavos(dados.limite)
            identificador = inserir(db, "cartoes", **campos)
            return apresentar(buscar(db, "cartoes", identificador))

    @app.get("/cartoes")
    def cartoes():
        return colecao("cartoes")

    @app.get("/cartoes/{cartao_id}")
    def cartao(cartao_id: int):
        return ler("cartoes", cartao_id)

    @app.put("/cartoes/{cartao_id}")
    def editar_cartao(cartao_id: int, dados: CartaoDados):
        with operacao() as (db, instante):
            registro = buscar(db, "cartoes", cartao_id)
            if registro["estado"] == "cancelado":
                raise HTTPException(409, "Cartao cancelado")
            if dados.estado == "ativo":
                validar_conta(db, buscar(db, "contas", registro["conta_id"]))
            atualizar(db, "cartoes", cartao_id, limite=centavos(dados.limite), estado=dados.estado)
            calendario(db, instante)
            return apresentar(buscar(db, "cartoes", cartao_id))

    @app.delete("/cartoes/{cartao_id}", status_code=204)
    def excluir_cartao(cartao_id: int):
        with operacao() as (db, _):
            buscar(db, "cartoes", cartao_id)
            atualizar(db, "cartoes", cartao_id, estado="cancelado")
        return Response(status_code=204)

    def registrar(db, conta_id, tipo, valor, instante, **vinculos):
        return inserir(
            db, "transacoes", conta_id=conta_id, tipo=tipo, valor=valor,
            data=instante.isoformat(), dia=instante.astimezone(FUSO_BANCARIO).date().isoformat(),
            estado="efetivada", **vinculos,
        )

    def tarifa_transferencia(db, origem, destino, cliente, transacao_id, instante):
        competencia = instante.astimezone(FUSO_BANCARIO).strftime("%Y-%m")
        franquia = REGRAS[cliente["categoria"]][3]
        usa_franquia = origem["cliente_id"] != destino["cliente_id"] and franquia is not None
        excedeu = False
        if usa_franquia:
            usadas = db.execute("""
                SELECT COUNT(*) FROM tarifas t JOIN contas co ON co.id = t.conta_id
                WHERE co.cliente_id = ? AND t.competencia = ? AND t.usa_franquia = 1
            """, (cliente["id"], competencia)).fetchone()[0]
            excedeu = usadas >= franquia
        identificador = inserir(
            db, "tarifas", conta_id=origem["id"], transacao_id=transacao_id,
            tipo="transferencia", valor=centavos(tarifa_excedente) if excedeu else 0,
            estado="pendente" if excedeu else "isenta", competencia=competencia,
            categoria=cliente["categoria"], usa_franquia=usa_franquia,
        )
        if excedeu:
            cobrar(db, buscar(db, "tarifas", identificador), instante)

    @app.post("/contas/{conta_id}/depositos", status_code=201)
    def depositar(conta_id: int, dados: Movimento):
        with operacao() as (db, instante):
            conta = buscar(db, "contas", conta_id)
            if conta["estado"] == "encerrada":
                raise HTTPException(409, "Conta encerrada")
            valor = centavos(dados.valor)
            saldo(db, conta, valor, instante)
            identificador = registrar(db, conta_id, "deposito", valor, instante)
            calendario(db, instante)
            return apresentar(buscar(db, "transacoes", identificador))

    @app.post("/contas/{conta_id}/saques", status_code=201)
    def sacar(conta_id: int, dados: Movimento):
        with operacao() as (db, instante):
            conta = buscar(db, "contas", conta_id)
            cliente = validar_conta(db, conta)
            dia = instante.astimezone(FUSO_BANCARIO).date().isoformat()
            acumulado = db.execute("""
                SELECT COALESCE(SUM(t.valor), 0) FROM transacoes t JOIN contas co ON co.id = t.conta_id
                WHERE co.cliente_id = ? AND t.dia = ? AND t.tipo = 'saque' AND t.estado = 'efetivada'
            """, (cliente["id"], dia)).fetchone()[0]
            valor = centavos(dados.valor)
            if acumulado + valor > REGRAS[cliente["categoria"]][0]:
                raise HTTPException(409, "Limite diario de saque excedido")
            saldo(db, conta, -valor, instante)
            identificador = registrar(db, conta_id, "saque", valor, instante)
            return apresentar(buscar(db, "transacoes", identificador))

    @app.post("/contas/{conta_id}/transferencias", status_code=201)
    def transferir(conta_id: int, dados: Transferencia):
        with operacao() as (db, instante):
            origem = buscar(db, "contas", conta_id)
            destino = buscar(db, "contas", dados.destino_id)
            if origem["id"] == destino["id"]:
                raise HTTPException(422, "Origem e destino devem ser diferentes")
            cliente = validar_conta(db, origem)
            validar_conta(db, destino)
            valor = centavos(dados.valor)
            if valor > REGRAS[cliente["categoria"]][1]:
                raise HTTPException(409, "Limite por transferencia excedido")
            saldo(db, origem, -valor, instante)
            saldo(db, destino, valor, instante)
            identificador = registrar(db, conta_id, "transferencia", valor, instante,
                                      destino_id=destino["id"])
            tarifa_transferencia(db, origem, destino, cliente, identificador, instante)
            return apresentar(buscar(db, "transacoes", identificador))

    @app.post("/transacoes/{transacao_id}/estorno", status_code=201)
    def estornar(transacao_id: int):
        with operacao() as (db, instante):
            original = buscar(db, "transacoes", transacao_id)
            if (original["estado"] != "efetivada" or original["tipo"] == "estorno"
                    or instante - datetime.fromisoformat(original["data"]) > timedelta(hours=24)):
                raise HTTPException(409, "Transacao indisponivel para estorno")
            origem = buscar(db, "contas", original["conta_id"])
            destino_id = original["destino_id"]
            destino = buscar(db, "contas", destino_id) if destino_id else None
            if origem["estado"] == "encerrada" or (destino and destino["estado"] == "encerrada"):
                raise HTTPException(409, "Conta encerrada impede o estorno")
            valor = original["valor"]
            diferenca = -valor if original["tipo"] == "deposito" else valor
            if destino:
                saldo(db, destino, -valor, instante)
            tarifa = db.execute("SELECT * FROM tarifas WHERE transacao_id = ?",
                                (transacao_id,)).fetchone()
            if tarifa:
                if tarifa["estado"] == "cobrada":
                    diferenca += tarifa["valor"]
                atualizar(db, "tarifas", tarifa["id"], estado="isenta", usa_franquia=0,
                          cobrada_em=None)
            saldo(db, origem, diferenca, instante)
            atualizar(db, "transacoes", transacao_id, estado="estornada")
            identificador = registrar(db, origem["id"], "estorno", valor, instante,
                                      destino_id=destino_id, original_id=transacao_id)
            return apresentar(buscar(db, "transacoes", identificador))

    @app.get("/contas/{conta_id}/extrato")
    def extrato(conta_id: int):
        with operacao() as (db, _):
            buscar(db, "contas", conta_id)
            return listar(db, """
                SELECT * FROM transacoes WHERE conta_id = ? OR destino_id = ? ORDER BY data, id
            """, (conta_id, conta_id))

    @app.get("/contas/{conta_id}/tarifas")
    def tarifas(conta_id: int):
        with operacao() as (db, _):
            buscar(db, "contas", conta_id)
            return listar(db, "SELECT * FROM tarifas WHERE conta_id = ? ORDER BY id", (conta_id,))

    @app.post("/cartoes/{cartao_id}/faturas", status_code=201)
    def criar_fatura(cartao_id: int, dados: Fatura):
        with operacao() as (db, instante):
            cartao = buscar(db, "cartoes", cartao_id)
            if cartao["estado"] != "ativo":
                raise HTTPException(409, "Cartao indisponivel para emitir fatura")
            campos = dados.model_dump(mode="json")
            campos["valor"] = centavos(dados.valor)
            identificador = inserir(db, "faturas", cartao_id=cartao_id, **campos)
            calendario(db, instante)
            return apresentar(buscar(db, "faturas", identificador))

    @app.get("/cartoes/{cartao_id}/faturas")
    def faturas(cartao_id: int):
        with operacao() as (db, _):
            buscar(db, "cartoes", cartao_id)
            return listar(db, "SELECT * FROM faturas WHERE cartao_id = ? ORDER BY mes_referencia",
                          (cartao_id,))

    @app.post("/faturas/{fatura_id}/pagamento")
    def pagar_fatura(fatura_id: int):
        with operacao() as (db, instante):
            fatura = buscar(db, "faturas", fatura_id)
            if fatura["estado"] == "paga":
                raise HTTPException(409, "Fatura ja paga")
            atualizar(db, "faturas", fatura_id, estado="paga", paga_em=instante.isoformat())
            return apresentar(buscar(db, "faturas", fatura_id))

    def periodo(inicio, fim):
        if fim < inicio:
            raise HTTPException(422, "Fim do periodo anterior ao inicio")
        return inicio.isoformat(), fim.isoformat()

    @app.get("/relatorios/movimentacao")
    def movimentacao(inicio: date, fim: date):
        datas = periodo(inicio, fim)
        with operacao() as (db, _):
            return listar(db, """
                WITH movimentos AS (
                    SELECT co.cliente_id, t.valor FROM transacoes t
                    JOIN contas co ON co.id = t.conta_id
                    WHERE t.estado = 'efetivada' AND t.tipo <> 'estorno' AND t.dia BETWEEN ? AND ?
                    UNION ALL
                    SELECT destino.cliente_id, t.valor FROM transacoes t
                    JOIN contas origem ON origem.id = t.conta_id
                    JOIN contas destino ON destino.id = t.destino_id
                    WHERE t.estado = 'efetivada' AND t.tipo = 'transferencia'
                    AND destino.cliente_id <> origem.cliente_id AND t.dia BETWEEN ? AND ?
                )
                SELECT c.id AS cliente_id, c.nome, SUM(m.valor) AS total FROM movimentos m
                JOIN clientes c ON c.id = m.cliente_id GROUP BY c.id ORDER BY total DESC, c.id
            """, (*datas, *datas))

    @app.get("/relatorios/saldos-negativos")
    def saldos_negativos():
        with operacao() as (db, _):
            return listar(db, "SELECT * FROM contas WHERE saldo < 0 ORDER BY saldo, id")

    @app.get("/relatorios/receita-tarifas")
    def receita_tarifas(inicio: date | None = None, fim: date | None = None):
        if (inicio is None) != (fim is None):
            raise HTTPException(422, "Informe inicio e fim juntos")
        filtro = ""
        parametros = ()
        if inicio is not None and fim is not None:
            parametros = periodo(inicio, fim)
            filtro = "AND date(cobrada_em, '-3 hours') BETWEEN ? AND ?"
        with operacao() as (db, _):
            receitas = listar(db, f"""
                SELECT categoria, SUM(valor) AS total FROM tarifas
                WHERE estado = 'cobrada' {filtro} GROUP BY categoria
            """, parametros)
            totais = {linha["categoria"]: linha["total"] for linha in receitas}
            return [{"categoria": categoria, "total": totais.get(categoria, "0.00")}
                    for categoria in REGRAS]

    return app


app = criar_app(tarifa_excedente=Decimal(os.getenv("BANCO_TARIFA_EXCEDENTE", "1.00")))




