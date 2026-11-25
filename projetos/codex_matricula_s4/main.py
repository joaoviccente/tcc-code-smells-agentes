import asyncio
import sqlite3
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse

import regras
from modelos import Aluno, Disciplina, Historico, PreRequisito, Semestre, Solicitacao, Turma


def processar_ofertas():
    with regras.transacao() as db:
        regras.expirar_ofertas(db, regras.agora())


async def monitorar_ofertas():
    while True:
        await asyncio.sleep(30)
        await asyncio.to_thread(processar_ofertas)


@asynccontextmanager
async def lifespan(_):
    regras.inicializar()
    processar_ofertas()
    tarefa = asyncio.create_task(monitorar_ofertas())
    try:
        yield
    finally:
        tarefa.cancel()
        with suppress(asyncio.CancelledError):
            await tarefa


app = FastAPI(title="API de Matriculas Academicas", lifespan=lifespan)


@app.exception_handler(sqlite3.IntegrityError)
async def conflito_banco(_, erro):
    mensagem = "Registro duplicado ou vinculado a outros registros"
    if erro.sqlite_errorname == "SQLITE_CONSTRAINT_FOREIGNKEY":
        mensagem = "O registro possui vinculos ou referencia um registro inexistente"
    return JSONResponse(status_code=409, content={"detail": mensagem})


def sessao():
    processar_ofertas()
    with regras.transacao() as db:
        yield db, regras.agora()


Sessao = Annotated[tuple[sqlite3.Connection, datetime], Depends(sessao, scope="function")]


def apresentar(tabela, item):
    if tabela == "turmas":
        item["horario"] = {campo: item.pop(campo) for campo in ("dia", "inicio", "fim")}
    return item


def salvar(db, tabela, dados, item_id=None):
    valores = dados.model_dump(mode="json")
    if tabela == "turmas":
        valores.update(valores.pop("horario"))
        regras.buscar(db, "disciplinas", valores["disciplina_id"])
        if item_id is not None:
            anterior = regras.buscar(db, tabela, item_id)
            confirmadas, reservadas = regras.ocupacao(db, item_id)
            vinculada = db.execute("SELECT 1 FROM matriculas WHERE turma_id = ?", (item_id,)).fetchone()
            if vinculada:
                regras.exigir(all(valores[campo] == anterior[campo] for campo in ("disciplina_id", "semestre")),
                               "Turma com matriculas registradas preserva disciplina e semestre")
            if confirmadas:
                regras.exigir(all(valores[campo] == anterior[campo] for campo in ("dia", "inicio", "fim")),
                               "Turma com matriculas confirmadas preserva o horario")
            regras.exigir(valores["estado"] == "cancelada" or valores["vagas"] >= confirmadas + reservadas,
                           "Total de vagas inferior a ocupacao")
            regras.exigir(valores["estado"] != "encerrada" or not reservadas,
                           "Resolva as ofertas de vaga antes de encerrar a turma")
            if valores["estado"] == "cancelada":
                regras.cancelar_registros(db, "turma_id = ?", (item_id,))
            elif valores["estado"] == "encerrada":
                regras.cancelar_registros(db, "turma_id = ? AND estado = 'lista_de_espera'", (item_id,))
    if item_id is None:
        colunas = ", ".join(valores)
        marcadores = ", ".join("?" for _ in valores)
        item_id = db.execute(
            f"INSERT INTO {tabela} ({colunas}) VALUES ({marcadores})", tuple(valores.values())
        ).lastrowid
    else:
        atribuicoes = ", ".join(f"{campo} = ?" for campo in valores)
        db.execute(f"UPDATE {tabela} SET {atribuicoes} WHERE id = ?", (*valores.values(), item_id))
    return item_id


def registrar_crud(tabela, modelo):
    caminho = f"/{tabela}"
    item = caminho + "/{item_id}"

    def listar(sessao: Sessao):
        db, _ = sessao
        return [apresentar(tabela, dict(row)) for row in db.execute(f"SELECT * FROM {tabela} ORDER BY id")]

    def obter(item_id: int, sessao: Sessao):
        return apresentar(tabela, regras.buscar(sessao[0], tabela, item_id))

    def criar(dados: modelo, sessao: Sessao):
        db, instante = sessao
        item_id = salvar(db, tabela, dados)
        if tabela == "turmas":
            regras.atualizar_fila(db, item_id, instante)
        return apresentar(tabela, regras.buscar(db, tabela, item_id))

    def atualizar(item_id: int, dados: modelo, sessao: Sessao):
        db, instante = sessao
        regras.buscar(db, tabela, item_id)
        salvar(db, tabela, dados, item_id)
        if tabela in ("disciplinas", "alunos"):
            validar_creditos(db, tabela, item_id)
        if tabela == "turmas":
            regras.atualizar_fila(db, item_id, instante)
        return apresentar(tabela, regras.buscar(db, tabela, item_id))

    def excluir(item_id: int, sessao: Sessao):
        db, _ = sessao
        regras.buscar(db, tabela, item_id)
        db.execute(f"DELETE FROM {tabela} WHERE id = ?", (item_id,))
        return Response(status_code=204)

    app.add_api_route(caminho, listar, methods=["GET"], name=f"listar_{tabela}", tags=[tabela])
    app.add_api_route(caminho, criar, methods=["POST"], status_code=201, name=f"criar_{tabela}", tags=[tabela])
    app.add_api_route(item, obter, methods=["GET"], name=f"obter_{tabela}", tags=[tabela])
    app.add_api_route(item, atualizar, methods=["PUT"], name=f"atualizar_{tabela}", tags=[tabela])
    app.add_api_route(item, excluir, methods=["DELETE"], status_code=204, name=f"excluir_{tabela}", tags=[tabela])


def validar_creditos(db, tabela, item_id):
    if tabela == "alunos":
        filtro = "a.id = ?"
    else:
        filtro = """a.id IN (SELECT m2.aluno_id FROM matriculas m2
                    JOIN turmas t2 ON t2.id = m2.turma_id
                    WHERE t2.disciplina_id = ? AND m2.estado = 'confirmada')"""
    totais = db.execute(
        f"""SELECT a.categoria, SUM(d.creditos) AS creditos FROM matriculas m
            JOIN alunos a ON a.id = m.aluno_id JOIN turmas t ON t.id = m.turma_id
            JOIN disciplinas d ON d.id = t.disciplina_id
            WHERE m.estado = 'confirmada' AND {filtro} GROUP BY a.id, t.semestre""",
        (item_id,),
    )
    for total in totais:
        regras.exigir(total["creditos"] <= regras.REGRAS[total["categoria"]].creditos,
                       "A alteracao excede o limite de creditos de matriculas confirmadas")


registrar_crud("alunos", Aluno)
registrar_crud("disciplinas", Disciplina)
registrar_crud("turmas", Turma)


@app.post("/disciplinas/{disciplina_id}/pre-requisitos", status_code=201)
def adicionar_pre_requisito(disciplina_id: int, dados: PreRequisito, sessao: Sessao):
    db, _ = sessao
    regras.buscar(db, "disciplinas", disciplina_id)
    regras.buscar(db, "disciplinas", dados.exigida_id)
    ciclo = db.execute(
        """WITH RECURSIVE cadeia(id) AS (
             SELECT ? UNION SELECT p.exigida_id FROM pre_requisitos p JOIN cadeia c ON c.id = p.disciplina_id
           ) SELECT 1 FROM cadeia WHERE id = ?""",
        (dados.exigida_id, disciplina_id),
    ).fetchone()
    regras.exigir(ciclo is None, "O pre-requisito cria um ciclo")
    db.execute("INSERT INTO pre_requisitos VALUES (?, ?)", (disciplina_id, dados.exigida_id))
    return {"disciplina_id": disciplina_id, "exigida_id": dados.exigida_id}


@app.get("/disciplinas/{disciplina_id}/pre-requisitos")
def listar_pre_requisitos(disciplina_id: int, sessao: Sessao):
    db, _ = sessao
    regras.buscar(db, "disciplinas", disciplina_id)
    return [dict(row) for row in db.execute(
        "SELECT * FROM pre_requisitos WHERE disciplina_id = ? ORDER BY exigida_id", (disciplina_id,)
    )]


@app.delete("/disciplinas/{disciplina_id}/pre-requisitos/{exigida_id}", status_code=204)
def excluir_pre_requisito(disciplina_id: int, exigida_id: int, sessao: Sessao):
    db, _ = sessao
    cursor = db.execute("DELETE FROM pre_requisitos WHERE disciplina_id = ? AND exigida_id = ?",
                        (disciplina_id, exigida_id))
    if not cursor.rowcount:
        raise HTTPException(404, "Pre-requisito nao encontrado")
    return Response(status_code=204)


@app.post("/matriculas", status_code=201)
def solicitar(dados: Solicitacao, sessao: Sessao):
    db, instante = sessao
    return regras.solicitar(db, dados, instante)


@app.post("/matriculas/{matricula_id}/confirmar")
def confirmar(matricula_id: int, sessao: Sessao):
    db, instante = sessao
    return regras.confirmar(db, matricula_id, instante)


@app.post("/matriculas/{matricula_id}/cancelar")
def cancelar(matricula_id: int, sessao: Sessao):
    db, instante = sessao
    return regras.desligar(db, matricula_id, instante)


@app.post("/matriculas/{matricula_id}/trancar")
def trancar(matricula_id: int, sessao: Sessao):
    db, instante = sessao
    return regras.desligar(db, matricula_id, instante, trancar=True)


@app.get("/alunos/{aluno_id}/matriculas")
def matriculas_do_aluno(aluno_id: int, sessao: Sessao):
    db, _ = sessao
    regras.buscar(db, "alunos", aluno_id)
    return [dict(row) for row in db.execute(
        "SELECT * FROM matriculas WHERE aluno_id = ? ORDER BY data, id", (aluno_id,)
    )]


@app.get("/turmas/{turma_id}/lista-de-espera")
def lista_de_espera(turma_id: int, sessao: Sessao):
    db, _ = sessao
    regras.buscar(db, "turmas", turma_id)
    ofertas = db.execute(
        """SELECT * FROM matriculas WHERE turma_id = ? AND estado = 'solicitada'
           ORDER BY oferta_ate, id""", (turma_id,)
    )
    return {
        "ofertas": [dict(row) for row in ofertas],
        "fila": [dict(row) for row in regras.fila(db, turma_id)],
    }


@app.post("/alunos/{aluno_id}/historico", status_code=201)
def registrar_historico(aluno_id: int, dados: Historico, sessao: Sessao):
    db, instante = sessao
    regras.buscar(db, "alunos", aluno_id)
    regras.buscar(db, "disciplinas", dados.disciplina_id)
    cursor = db.execute(
        """INSERT INTO historico (aluno_id, disciplina_id, semestre, nota, situacao)
           VALUES (?, ?, ?, ?, ?)""",
        (aluno_id, dados.disciplina_id, dados.semestre, dados.nota, dados.situacao),
    )
    if dados.situacao == "trancado":
        for turma_id in regras.aplicar_trancamento_semestral(db, aluno_id, dados.semestre):
            regras.atualizar_fila(db, turma_id, instante)
    return regras.buscar(db, "historico", cursor.lastrowid)


@app.get("/alunos/{aluno_id}/historico")
def historico_do_aluno(aluno_id: int, sessao: Sessao):
    db, _ = sessao
    regras.buscar(db, "alunos", aluno_id)
    return [dict(row) for row in db.execute(
        "SELECT * FROM historico WHERE aluno_id = ? ORDER BY semestre, id", (aluno_id,)
    )]


@app.post("/periodos-matricula/{semestre}/encerrar")
def encerrar_periodo(semestre: Semestre, sessao: Sessao):
    db, instante = sessao
    turmas = db.execute("SELECT id, estado FROM turmas WHERE semestre = ? ORDER BY id", (semestre,)).fetchall()
    if not turmas:
        raise HTTPException(404, "Semestre sem turmas")
    cursor = db.execute(
        "INSERT INTO periodos_encerrados VALUES (?, ?) ON CONFLICT DO NOTHING", (semestre, instante.isoformat())
    )
    if cursor.rowcount:
        for turma in turmas:
            turma_id = turma["id"]
            if turma["estado"] != "cancelada" and regras.ocupacao(db, turma_id)["confirmadas"] < 5:
                db.execute("UPDATE turmas SET estado = 'cancelada' WHERE id = ?", (turma_id,))
                regras.cancelar_registros(db, "turma_id = ?", (turma_id,))
    return {"semestre": semestre, "turmas_canceladas": [row["id"] for row in db.execute(
        "SELECT id FROM turmas WHERE semestre = ? AND estado = 'cancelada' ORDER BY id", (semestre,)
    )]}


@app.get("/relatorios/disciplinas-mais-procuradas")
def disciplinas_mais_procuradas(semestre: Semestre, sessao: Sessao):
    db, _ = sessao
    return [dict(row) for row in db.execute(
        """SELECT d.id AS disciplina_id, d.codigo, d.nome, COUNT(m.id) AS solicitacoes
           FROM disciplinas d JOIN turmas t ON t.disciplina_id = d.id
           JOIN matriculas m ON m.turma_id = t.id WHERE t.semestre = ?
           GROUP BY d.id ORDER BY solicitacoes DESC, d.codigo""", (semestre,)
    )]


@app.get("/relatorios/taxa-reprovacao")
def taxa_reprovacao(sessao: Sessao, semestre: Annotated[Semestre | None, Query()] = None):
    db, _ = sessao
    return [dict(row) for row in db.execute(
        """SELECT d.id AS disciplina_id, d.codigo, d.nome, COUNT(h.id) AS avaliadas,
                  COUNT(CASE WHEN h.situacao = 'reprovado' THEN 1 END) AS reprovacoes,
                  1.0 * COUNT(CASE WHEN h.situacao = 'reprovado' THEN 1 END)
                    / NULLIF(COUNT(h.id), 0) AS taxa
           FROM disciplinas d LEFT JOIN historico h ON h.disciplina_id = d.id
             AND h.situacao IN ('aprovado', 'reprovado') AND (? IS NULL OR h.semestre = ?)
           GROUP BY d.id ORDER BY d.codigo""", (semestre, semestre)
    )]


@app.get("/relatorios/ocupacao-turmas")
def ocupacao_turmas(sessao: Sessao, semestre: Annotated[Semestre | None, Query()] = None):
    db, _ = sessao
    return [dict(row) for row in db.execute(
        """WITH ocupacoes AS (
               SELECT turma_id, COUNT(*) AS confirmadas FROM matriculas
               WHERE estado = 'confirmada' GROUP BY turma_id
           )
           SELECT d.departamento, COUNT(t.id) AS turmas, SUM(t.vagas) AS vagas,
                  SUM(COALESCE(o.confirmadas, 0)) AS confirmadas,
                  1.0 * SUM(COALESCE(o.confirmadas, 0)) / SUM(t.vagas) AS taxa
           FROM turmas t JOIN disciplinas d ON d.id = t.disciplina_id
           LEFT JOIN ocupacoes o ON o.turma_id = t.id
           WHERE t.estado <> 'cancelada' AND (? IS NULL OR t.semestre = ?)
           GROUP BY d.departamento ORDER BY d.departamento""", (semestre, semestre)
    )]
