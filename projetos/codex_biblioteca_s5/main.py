import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.responses import JSONResponse

import biblioteca as b
from modelos import Exemplar, Livro, NovaReserva, NovoEmprestimo, Usuario

Id = Annotated[int, Path(gt=0)]
UsuarioId = Annotated[int, Query(gt=0)]


def atualizar_relogio():
    with b.transacao() as db:
        agora = b.relogio()
        b.sincronizar(db, agora, b.dia_local(agora))


async def rotina():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(atualizar_relogio)
        except sqlite3.OperationalError:
            logging.exception("Falha na atualizacao periodica da biblioteca")


@asynccontextmanager
async def lifespan(app):
    b.inicializar()
    atualizar_relogio()
    tarefa = asyncio.create_task(rotina())
    try:
        yield
    finally:
        tarefa.cancel()
        await asyncio.gather(tarefa, return_exceptions=True)


app = FastAPI(title="Biblioteca Universitaria", lifespan=lifespan)


@app.exception_handler(sqlite3.IntegrityError)
def erro_integridade(request: Request, erro: sqlite3.IntegrityError):
    mensagem = "Valor ja cadastrado ou operacao conflitante"
    if erro.sqlite_errorname in {"SQLITE_CONSTRAINT_FOREIGNKEY", "SQLITE_CONSTRAINT_TRIGGER"}:
        mensagem = "O registro possui vinculos e nao pode ser excluido"
    return JSONResponse(status_code=409, content={"detail": mensagem})


def contexto():
    with b.transacao() as db:
        agora = b.relogio()
        hoje = b.dia_local(agora)
        b.sincronizar(db, agora, hoje)
        db.execute("SAVEPOINT operacao")
        try:
            yield db, agora, hoje
        except (HTTPException, sqlite3.IntegrityError) as erro:
            db.execute("ROLLBACK TO operacao")
            falha = erro
        else:
            falha = None
    if falha is not None:
        raise falha


Contexto = Annotated[tuple, Depends(contexto, scope="function")]


def listar(db, tabela):
    return [dict(item) for item in db.execute(f"SELECT * FROM {tabela} ORDER BY id")]


def gravar(db, tabela, dados, id=None):
    colunas = tuple(dados)
    if id is None:
        parametros = ", ".join("?" for _ in colunas)
        cursor = db.execute(
            f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({parametros})",
            tuple(dados.values()),
        )
        id = cursor.lastrowid
    else:
        atribuicoes = ", ".join(f"{coluna} = ?" for coluna in colunas)
        db.execute(f"UPDATE {tabela} SET {atribuicoes} WHERE id = ?", (*dados.values(), id))
    return b.obter(db, tabela, id)


def excluir(db, tabela, id):
    cursor = db.execute(f"DELETE FROM {tabela} WHERE id = ?", (id,))
    if cursor.rowcount == 0:
        raise HTTPException(404, "Registro nao encontrado")
    return Response(status_code=204)


def dados_usuario(entrada):
    dados = entrada.model_dump()
    dados["situacao_manual"] = dados.pop("situacao")
    return dados


@app.post("/usuarios", status_code=201)
def criar_usuario(entrada: Usuario, ctx: Contexto):
    db, _, hoje = ctx
    return b.usuario_publico(gravar(db, "usuarios", dados_usuario(entrada)), hoje)


@app.get("/usuarios")
def listar_usuarios(ctx: Contexto):
    db, _, hoje = ctx
    return [b.usuario_publico(usuario, hoje) for usuario in listar(db, "usuarios")]


@app.get("/usuarios/{id}")
def consultar_usuario(id: Id, ctx: Contexto):
    db, _, hoje = ctx
    return b.usuario_publico(b.obter(db, "usuarios", id), hoje)


@app.put("/usuarios/{id}")
def atualizar_usuario(id: Id, entrada: Usuario, ctx: Contexto):
    db, _, hoje = ctx
    return b.usuario_publico(gravar(db, "usuarios", dados_usuario(entrada), id), hoje)


@app.delete("/usuarios/{id}", status_code=204)
def excluir_usuario(id: Id, ctx: Contexto):
    return excluir(ctx[0], "usuarios", id)


@app.post("/livros", status_code=201)
def criar_livro(entrada: Livro, ctx: Contexto):
    return gravar(ctx[0], "livros", entrada.model_dump())


@app.get("/livros")
def listar_livros(ctx: Contexto):
    return listar(ctx[0], "livros")


@app.get("/livros/{id}")
def consultar_livro(id: Id, ctx: Contexto):
    return b.obter(ctx[0], "livros", id)


@app.put("/livros/{id}")
def atualizar_livro(id: Id, entrada: Livro, ctx: Contexto):
    return gravar(ctx[0], "livros", entrada.model_dump(), id)


@app.delete("/livros/{id}", status_code=204)
def excluir_livro(id: Id, ctx: Contexto):
    return excluir(ctx[0], "livros", id)


@app.post("/exemplares", status_code=201)
def criar_exemplar(entrada: Exemplar, ctx: Contexto):
    db, agora, _ = ctx
    b.obter(db, "livros", entrada.livro_id)
    b.exigir(entrada.estado not in {"emprestado", "reservado"}, "Estado depende de emprestimo ou reserva")
    exemplar = gravar(db, "exemplares", entrada.model_dump())
    b.distribuir(db, entrada.livro_id, agora)
    return b.obter(db, "exemplares", exemplar["id"])


@app.get("/exemplares")
def listar_exemplares(ctx: Contexto):
    return listar(ctx[0], "exemplares")


@app.get("/exemplares/{id}")
def consultar_exemplar(id: Id, ctx: Contexto):
    return b.obter(ctx[0], "exemplares", id)


@app.put("/exemplares/{id}")
def atualizar_exemplar(id: Id, entrada: Exemplar, ctx: Contexto):
    db, agora, _ = ctx
    exemplar = b.obter(db, "exemplares", id)
    b.obter(db, "livros", entrada.livro_id)
    em_circulacao = {"emprestado", "reservado"}
    if exemplar["estado"] in em_circulacao or entrada.estado in em_circulacao:
        b.exigir(
            exemplar["estado"] == entrada.estado and exemplar["livro_id"] == entrada.livro_id,
            "Estado e livro dependem do emprestimo ou reserva",
        )
    if exemplar["livro_id"] != entrada.livro_id:
        historico = db.execute("SELECT 1 FROM emprestimos WHERE exemplar_id = ? LIMIT 1", (id,)).fetchone()
        b.exigir(historico is None, "Exemplar com historico de emprestimo")
    gravar(db, "exemplares", entrada.model_dump(), id)
    if entrada.estado == "baixado":
        b.cancelar_reservas_se_baixa(db, exemplar["livro_id"], exemplar["estado"] == "disponivel")
    elif exemplar["livro_id"] != entrada.livro_id:
        b.cancelar_reservas_se_baixa(db, exemplar["livro_id"])
    b.distribuir(db, entrada.livro_id, agora)
    return b.obter(db, "exemplares", id)


@app.delete("/exemplares/{id}", status_code=204)
def excluir_exemplar(id: Id, ctx: Contexto):
    db, _, _ = ctx
    exemplar = b.obter(db, "exemplares", id)
    b.exigir(exemplar["estado"] not in {"emprestado", "reservado"}, "Exemplar em circulacao")
    resposta = excluir(db, "exemplares", id)
    b.cancelar_reservas_se_baixa(db, exemplar["livro_id"])
    return resposta


@app.post("/emprestimos", status_code=201)
def criar_emprestimo(entrada: NovoEmprestimo, ctx: Contexto):
    db, _, hoje = ctx
    usuario = b.usuario_publico(b.obter(db, "usuarios", entrada.usuario_id), hoje)
    exemplar = b.obter(db, "exemplares", entrada.exemplar_id)
    politica = b.POLITICAS[usuario["categoria"]]
    b.exigir(usuario["situacao"] == "ativo", "Usuario suspenso")
    multa = db.execute(
        """SELECT 1 FROM multas m JOIN emprestimos e ON e.id = m.emprestimo_id
           WHERE e.usuario_id = ? AND m.estado = 'aberta' LIMIT 1""",
        (entrada.usuario_id,),
    ).fetchone()
    b.exigir(multa is None, "Usuario possui multa aberta")
    total = db.execute(
        "SELECT COUNT(*) FROM emprestimos WHERE usuario_id = ? AND data_devolucao IS NULL",
        (entrada.usuario_id,),
    ).fetchone()[0]
    b.exigir(total < politica.limite, "Limite de emprestimos atingido")
    reserva = db.execute(
        "SELECT * FROM reservas WHERE exemplar_id = ? AND estado = 'disponivel'",
        (entrada.exemplar_id,),
    ).fetchone()
    if exemplar["estado"] == "reservado":
        b.exigir(reserva is not None and reserva["usuario_id"] == entrada.usuario_id, "Exemplar reservado")
        db.execute("UPDATE reservas SET estado = 'atendida' WHERE id = ?", (reserva["id"],))
    else:
        b.exigir(exemplar["estado"] == "disponivel", "Exemplar indisponivel")
    db.execute("UPDATE exemplares SET estado = 'emprestado' WHERE id = ?", (entrada.exemplar_id,))
    return gravar(db, "emprestimos", entrada.model_dump() | {
        "categoria": usuario["categoria"],
        "data_retirada": hoje.isoformat(),
        "data_prevista": (hoje + timedelta(days=politica.prazo)).isoformat(),
        "estado": "ativo",
    })


@app.get("/emprestimos")
def listar_emprestimos(usuario_id: UsuarioId, ctx: Contexto):
    db = ctx[0]
    b.obter(db, "usuarios", usuario_id)
    return [dict(item) for item in db.execute(
        "SELECT * FROM emprestimos WHERE usuario_id = ? ORDER BY id", (usuario_id,)
    )]


@app.post("/emprestimos/{id}/renovar")
def renovar_emprestimo(id: Id, ctx: Contexto):
    db, _, _ = ctx
    emprestimo = b.obter(db, "emprestimos", id)
    b.exigir(emprestimo["estado"] == "ativo", "Emprestimo devolvido ou atrasado")
    politica = b.POLITICAS[emprestimo["categoria"]]
    b.exigir(emprestimo["numero_renovacoes"] < politica.renovacoes, "Limite de renovacoes atingido")
    exemplar = b.obter(db, "exemplares", emprestimo["exemplar_id"])
    b.exigir(not b.fila_reservas(db, exemplar["livro_id"]), "Livro possui fila de reservas")
    prevista = date.fromisoformat(emprestimo["data_prevista"]) + timedelta(days=politica.prazo)
    return gravar(db, "emprestimos", {
        "data_prevista": prevista.isoformat(),
        "numero_renovacoes": emprestimo["numero_renovacoes"] + 1,
    }, id)


@app.post("/emprestimos/{id}/devolver")
def devolver_emprestimo(id: Id, ctx: Contexto):
    db, agora, hoje = ctx
    emprestimo = b.obter(db, "emprestimos", id)
    b.exigir(emprestimo["data_devolucao"] is None, "Emprestimo ja devolvido")
    exemplar = b.obter(db, "exemplares", emprestimo["exemplar_id"])
    baixado = b.dias_atraso(emprestimo, hoje) > 60
    gravar(db, "exemplares", {"estado": "baixado" if baixado else "disponivel"}, exemplar["id"])
    if baixado:
        b.atualizar_multa(db, emprestimo, b.dias_atraso(emprestimo, hoje), baixado=True)
        b.cancelar_reservas_se_baixa(db, exemplar["livro_id"])
    else:
        b.distribuir(db, exemplar["livro_id"], agora)
    return gravar(db, "emprestimos", {"data_devolucao": hoje.isoformat(), "estado": "devolvido"}, id)


@app.post("/reservas", status_code=201)
def criar_reserva(entrada: NovaReserva, ctx: Contexto):
    db, agora, _ = ctx
    b.obter(db, "livros", entrada.livro_id)
    b.obter(db, "usuarios", entrada.usuario_id)
    estoque = db.execute(
        """SELECT 1 FROM exemplares WHERE livro_id = ?
           AND estado IN ('disponivel', 'emprestado', 'reservado') LIMIT 1""",
        (entrada.livro_id,),
    ).fetchone()
    b.exigir(estoque is not None, "Livro sem exemplares aptos para reserva")
    reserva = gravar(db, "reservas", entrada.model_dump() | {"estado": "aguardando", "data": agora.isoformat()})
    b.distribuir(db, entrada.livro_id, agora)
    return b.reserva_publica(db, reserva["id"])


@app.post("/reservas/{id}/cancelar")
def cancelar_reserva(id: Id, ctx: Contexto):
    db, agora, _ = ctx
    reserva = b.obter(db, "reservas", id)
    b.exigir(reserva["estado"] in {"aguardando", "disponivel"}, "Reserva encerrada")
    b.liberar_reserva(db, reserva, "cancelada")
    b.distribuir(db, reserva["livro_id"], agora)
    return b.reserva_publica(db, id)


@app.get("/livros/{id}/reservas")
def listar_fila(id: Id, ctx: Contexto):
    db = ctx[0]
    b.obter(db, "livros", id)
    return b.fila_reservas(db, id)


@app.get("/multas")
def listar_multas(usuario_id: UsuarioId, ctx: Contexto):
    db = ctx[0]
    b.obter(db, "usuarios", usuario_id)
    return [b.multa_publica(item) for item in db.execute(
        """SELECT m.* FROM multas m JOIN emprestimos e ON e.id = m.emprestimo_id
           WHERE e.usuario_id = ? ORDER BY m.id""", (usuario_id,)
    )]


@app.post("/multas/{id}/pagar")
def pagar_multa(id: Id, ctx: Contexto):
    db = ctx[0]
    multa = b.obter(db, "multas", id)
    b.exigir(multa["estado"] == "aberta", "Multa sem saldo aberto")
    atualizada = gravar(db, "multas", {"estado": "paga", "centavos_pagos": multa["centavos"]}, id)
    return b.multa_publica(atualizada)


@app.get("/relatorios/livros-mais-emprestados")
def livros_mais_emprestados(inicio: date, fim: date, ctx: Contexto):
    if inicio > fim:
        raise HTTPException(422, "Inicio deve ser anterior ou igual ao fim")
    return [dict(item) for item in ctx[0].execute(
        """SELECT l.id AS livro_id, l.titulo, COUNT(*) AS total_emprestimos
           FROM emprestimos e JOIN exemplares x ON x.id = e.exemplar_id
           JOIN livros l ON l.id = x.livro_id WHERE e.data_retirada BETWEEN ? AND ?
           GROUP BY l.id ORDER BY total_emprestimos DESC, l.id""",
        (inicio.isoformat(), fim.isoformat()),
    )]


@app.get("/relatorios/usuarios-com-mais-atrasos")
def usuarios_com_mais_atrasos(ctx: Contexto):
    return [dict(item) for item in ctx[0].execute(
        """SELECT u.id AS usuario_id, u.nome, COUNT(*) AS total_atrasos
           FROM emprestimos e JOIN usuarios u ON u.id = e.usuario_id
           WHERE e.estado = 'atrasado' OR e.data_devolucao > e.data_prevista
           GROUP BY u.id ORDER BY total_atrasos DESC, u.id"""
    )]


@app.get("/relatorios/ocupacao-por-area")
def ocupacao_por_area(ctx: Contexto):
    return [dict(item) for item in ctx[0].execute(
        """SELECT l.area_conhecimento, COUNT(x.id) AS total_exemplares,
                  COUNT(CASE WHEN x.estado = 'emprestado' THEN 1 END) AS total_emprestados,
                  COALESCE(ROUND(100.0 * COUNT(CASE WHEN x.estado = 'emprestado' THEN 1 END)
                                 / NULLIF(COUNT(x.id), 0), 2), 0) AS taxa_ocupacao
           FROM livros l LEFT JOIN exemplares x ON x.livro_id = l.id AND x.estado <> 'baixado'
           GROUP BY l.area_conhecimento ORDER BY l.area_conhecimento"""
    )]
