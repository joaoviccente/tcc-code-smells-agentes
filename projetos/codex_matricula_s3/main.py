import asyncio
import json
import logging
import sqlite3
from contextlib import asynccontextmanager, suppress
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Request, Response
from fastapi.responses import JSONResponse

import matriculas as regras
from banco import inicializar, transacao
from modelos import Aluno, Disciplina, Historico, PreRequisito, Semestre, Solicitacao, Turma

Id = Annotated[int, Path(gt=0)]


def processar_prazos():
    with transacao() as db:
        regras.expirar_ofertas(db, regras.agora())


async def monitorar_prazos():
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.to_thread(processar_prazos)
        except sqlite3.Error:
            logging.exception("Falha ao processar os prazos da lista de espera.")


@asynccontextmanager
async def lifespan(app):
    inicializar()
    processar_prazos()
    tarefa = asyncio.create_task(monitorar_prazos())
    try:
        yield
    finally:
        tarefa.cancel()
        with suppress(asyncio.CancelledError):
            await tarefa


app = FastAPI(title="Matrículas acadêmicas", lifespan=lifespan)


@app.exception_handler(sqlite3.IntegrityError)
async def conflito_integridade(request: Request, erro: sqlite3.IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Registro duplicado ou vinculado a outros registros."})


def banco():
    processar_prazos()
    with transacao() as db:
        yield db


Banco = Annotated[sqlite3.Connection, Depends(banco, scope="function")]


def apresentar(tabela, item):
    dados = dict(item)
    if tabela == "turmas":
        dados["horario"] = json.loads(dados["horario"])
    return dados


def salvar(db, tabela, entrada, identificador=None):
    dados = entrada.model_dump(mode="json")
    if tabela == "turmas":
        regras.obter(db, "disciplinas", dados["disciplina_id"])
        dados["horario"] = json.dumps(dados["horario"])
        if identificador is not None:
            anterior = regras.obter(db, tabela, identificador)
            vinculada = db.execute("SELECT 1 FROM matriculas WHERE turma_id = ?", (identificador,)).fetchone()
            campos = ("disciplina_id", "semestre", "horario")
            regras.exigir(not vinculada or all(dados[campo] == anterior[campo] for campo in campos),
                          "Turmas com matrículas preservam disciplina, semestre e horário.")
            regras.exigir(dados["vagas"] >= regras.ocupadas(db, identificador)
                          or dados["estado"] in ("cancelada", "encerrada"),
                          "Vagas abaixo do total de matrículas confirmadas e reservas.")
            regras.exigir(anterior["estado"] != "cancelada" or dados["estado"] == "cancelada",
                          "Turma cancelada não pode ser reaberta.")
        encerrado = db.execute("SELECT 1 FROM periodos_encerrados WHERE semestre = ?",
                               (dados["semestre"],)).fetchone()
        if encerrado and dados["estado"] in ("aberta", "lotada"):
            regras.exigir(identificador is not None and anterior["estado"] in ("aberta", "lotada"),
                          "Período de matrícula encerrado.")
    if identificador is None:
        campos = ", ".join(dados)
        marcadores = ", ".join("?" for _ in dados)
        identificador = db.execute(f"INSERT INTO {tabela} ({campos}) VALUES ({marcadores})",
                                   tuple(dados.values())).lastrowid
    else:
        regras.obter(db, tabela, identificador)
        campos = ", ".join(f"{campo} = ?" for campo in dados)
        db.execute(f"UPDATE {tabela} SET {campos} WHERE id = ?", (*dados.values(), identificador))
    if tabela == "turmas":
        if dados["estado"] in ("cancelada", "encerrada"):
            regras.cancelar_turma(db, identificador, dados["estado"])
        else:
            regras.atualizar_fila(db, identificador, regras.agora())
    return apresentar(tabela, regras.obter(db, tabela, identificador))


def registrar_crud(tabela, modelo):
    def listar(db: Banco):
        return [apresentar(tabela, item) for item in db.execute(f"SELECT * FROM {tabela} ORDER BY id")]

    def consultar(identificador: Id, db: Banco):
        return apresentar(tabela, regras.obter(db, tabela, identificador))

    def criar(entrada: modelo, db: Banco):
        return salvar(db, tabela, entrada)

    def atualizar(identificador: Id, entrada: modelo, db: Banco):
        return salvar(db, tabela, entrada, identificador)

    def excluir(identificador: Id, db: Banco):
        regras.obter(db, tabela, identificador)
        db.execute(f"DELETE FROM {tabela} WHERE id = ?", (identificador,))
        return Response(status_code=204)

    colecao = f"/{tabela}"
    recurso = colecao + "/{identificador}"
    app.add_api_route(colecao, listar, methods=["GET"], name=f"listar_{tabela}")
    app.add_api_route(colecao, criar, methods=["POST"], name=f"criar_{tabela}", status_code=201)
    app.add_api_route(recurso, consultar, methods=["GET"], name=f"consultar_{tabela}")
    app.add_api_route(recurso, atualizar, methods=["PUT"], name=f"atualizar_{tabela}")
    app.add_api_route(recurso, excluir, methods=["DELETE"], name=f"excluir_{tabela}", status_code=204)


registrar_crud("alunos", Aluno)
registrar_crud("disciplinas", Disciplina)
registrar_crud("turmas", Turma)


@app.post("/matriculas", status_code=201)
def solicitar(entrada: Solicitacao, db: Banco):
    return regras.solicitar(db, entrada.aluno_id, entrada.turma_id, regras.agora())


@app.post("/matriculas/{identificador}/confirmar")
def confirmar(identificador: Id, db: Banco):
    return regras.confirmar(db, identificador, regras.agora())


@app.post("/matriculas/{identificador}/cancelar")
def cancelar(identificador: Id, db: Banco):
    return regras.alterar_matricula(db, identificador, False, regras.agora())


@app.post("/matriculas/{identificador}/trancar")
def trancar(identificador: Id, db: Banco):
    return regras.alterar_matricula(db, identificador, True, regras.agora())


@app.get("/alunos/{aluno_id}/matriculas")
def listar_matriculas(aluno_id: Id, db: Banco):
    regras.obter(db, "alunos", aluno_id)
    return [dict(item) for item in db.execute("SELECT * FROM matriculas WHERE aluno_id = ? ORDER BY id", (aluno_id,))]


@app.get("/turmas/{turma_id}/lista-de-espera")
def consultar_fila(turma_id: Id, db: Banco):
    regras.obter(db, "turmas", turma_id)
    return regras.fila(db, turma_id)


@app.get("/alunos/{aluno_id}/historico")
def consultar_historico(aluno_id: Id, db: Banco):
    regras.obter(db, "alunos", aluno_id)
    return [dict(item) for item in db.execute("""
        SELECT * FROM historico WHERE aluno_id = ? ORDER BY semestre, id
    """, (aluno_id,))]


@app.post("/alunos/{aluno_id}/historico", status_code=201)
def registrar_historico(aluno_id: Id, entrada: Historico, db: Banco):
    regras.obter(db, "alunos", aluno_id)
    regras.obter(db, "disciplinas", entrada.disciplina_id)
    registro = db.execute("""
        INSERT INTO historico (aluno_id, disciplina_id, semestre, nota, situacao)
        VALUES (?, ?, ?, ?, ?)
    """, (aluno_id, entrada.disciplina_id, entrada.semestre, entrada.nota, entrada.situacao)).lastrowid
    return regras.obter(db, "historico", registro)


@app.get("/disciplinas/{disciplina_id}/pre-requisitos")
def listar_pre_requisitos(disciplina_id: Id, db: Banco):
    regras.obter(db, "disciplinas", disciplina_id)
    return [dict(item) for item in db.execute("""
        SELECT * FROM pre_requisitos WHERE disciplina_id = ? ORDER BY exigida_id
    """, (disciplina_id,))]


@app.post("/disciplinas/{disciplina_id}/pre-requisitos", status_code=201)
def registrar_pre_requisito(disciplina_id: Id, entrada: PreRequisito, db: Banco):
    regras.obter(db, "disciplinas", disciplina_id)
    regras.obter(db, "disciplinas", entrada.exigida_id)
    ciclo = db.execute("""
        WITH RECURSIVE exigidas(id) AS (
            SELECT ? UNION SELECT p.exigida_id FROM pre_requisitos p JOIN exigidas e ON p.disciplina_id = e.id
        )
        SELECT 1 FROM exigidas WHERE id = ?
    """, (entrada.exigida_id, disciplina_id)).fetchone()
    regras.exigir(not ciclo, "Pré-requisito circular.")
    db.execute("INSERT INTO pre_requisitos VALUES (?, ?)", (disciplina_id, entrada.exigida_id))
    return {"disciplina_id": disciplina_id, "exigida_id": entrada.exigida_id}


@app.delete("/disciplinas/{disciplina_id}/pre-requisitos/{exigida_id}", status_code=204)
def excluir_pre_requisito(disciplina_id: Id, exigida_id: Id, db: Banco):
    removidos = db.execute("DELETE FROM pre_requisitos WHERE disciplina_id = ? AND exigida_id = ?",
                           (disciplina_id, exigida_id)).rowcount
    if not removidos:
        raise HTTPException(404, "Pré-requisito não encontrado.")
    return Response(status_code=204)


@app.post("/periodos/{semestre}/encerrar")
def encerrar_periodo(semestre: Semestre, db: Banco):
    inserido = db.execute("INSERT OR IGNORE INTO periodos_encerrados VALUES (?)", (semestre,)).rowcount
    turmas = []
    if inserido:
        turmas = [item["id"] for item in db.execute("""
            SELECT t.id FROM turmas t LEFT JOIN matriculas m ON m.turma_id = t.id AND m.estado = 'confirmada'
            WHERE t.semestre = ? AND t.estado <> 'cancelada'
            GROUP BY t.id HAVING COUNT(m.id) < 5 ORDER BY t.id
        """, (semestre,))]
        for turma_id in turmas:
            regras.cancelar_turma(db, turma_id)
    return {"semestre": semestre, "turmas_canceladas": turmas}


@app.get("/relatorios/disciplinas-mais-procuradas")
def demanda(semestre: Semestre, db: Banco):
    return [dict(item) for item in db.execute("""
        SELECT d.id AS disciplina_id, d.codigo, d.nome, COUNT(m.id) AS solicitacoes
        FROM disciplinas d JOIN turmas t ON t.disciplina_id = d.id
        LEFT JOIN matriculas m ON m.turma_id = t.id WHERE t.semestre = ?
        GROUP BY d.id ORDER BY solicitacoes DESC, d.codigo
    """, (semestre,))]


@app.get("/relatorios/taxa-reprovacao")
def taxa_reprovacao(db: Banco, semestre: Semestre | None = None):
    return [dict(item) for item in db.execute("""
        SELECT d.id AS disciplina_id, d.codigo, d.nome, COUNT(h.id) AS resultados,
               COUNT(CASE WHEN h.situacao = 'reprovado' THEN 1 END) AS reprovacoes,
               1.0 * COUNT(CASE WHEN h.situacao = 'reprovado' THEN 1 END)
                   / NULLIF(COUNT(h.id), 0) AS taxa_reprovacao
        FROM disciplinas d LEFT JOIN historico h ON h.disciplina_id = d.id
            AND h.situacao IN ('aprovado', 'reprovado') AND (? IS NULL OR h.semestre = ?)
        GROUP BY d.id ORDER BY d.codigo
    """, (semestre, semestre))]


@app.get("/relatorios/ocupacao")
def ocupacao(db: Banco, semestre: Semestre | None = None, departamento: str | None = None):
    return [dict(item) for item in db.execute("""
        SELECT d.departamento, t.id AS turma_id, t.semestre, t.vagas, t.estado,
               COUNT(m.id) AS confirmadas, 1.0 * COUNT(m.id) / t.vagas AS taxa_ocupacao
        FROM turmas t JOIN disciplinas d ON d.id = t.disciplina_id
        LEFT JOIN matriculas m ON m.turma_id = t.id AND m.estado = 'confirmada'
        WHERE (? IS NULL OR t.semestre = ?) AND (? IS NULL OR d.departamento = ?)
        GROUP BY t.id ORDER BY d.departamento, t.semestre, t.id
    """, (semestre, semestre, departamento, departamento))]
