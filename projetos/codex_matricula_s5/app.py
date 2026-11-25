import asyncio
import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path as ApiPath, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

import modelos
import servico as s

Id = Annotated[int, ApiPath(gt=0)]
logger = logging.getLogger(__name__)


def gravar(db, tabela, dados, id=None):
    colunas = list(dados)
    if id is None:
        valores = ", ".join("?" for _ in colunas)
        retorno = db.execute(
            f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({valores}) RETURNING *",
            tuple(dados.values()),
        )
    else:
        atribuicoes = ", ".join(f"{coluna} = ?" for coluna in colunas)
        retorno = db.execute(
            f"UPDATE {tabela} SET {atribuicoes} WHERE id = ? RETURNING *",
            (*dados.values(), id),
        )
    return s.serializar(retorno.fetchone())


def listar(db, sql, *params):
    return [s.serializar(linha) for linha in db.execute(sql, params)]


def conexao(request: Request):
    caminho = request.app.state.caminho
    with s.transacao(caminho) as db:
        s.expirar_reservas(db, s.agora())
        db.execute("SAVEPOINT operacao")
        try:
            yield db
        except Exception:
            db.execute("ROLLBACK TO operacao")
            db.execute("RELEASE operacao")
            db.commit()
            raise


Banco = Annotated[sqlite3.Connection, Depends(conexao, scope="function")]


def criar_crud(app, tabela, modelo, preparar=None):
    rota = f"/{tabela}"

    @app.post(rota, status_code=201, name=f"criar_{tabela}", tags=[tabela])
    def criar(dados: modelo, db: Banco):
        valores = dados.model_dump(mode="json")
        if preparar:
            preparar(db, valores)
        return gravar(db, tabela, valores)

    @app.get(rota, name=f"listar_{tabela}", tags=[tabela])
    def todos(db: Banco):
        return listar(db, f"SELECT * FROM {tabela} ORDER BY id")

    @app.get(f"{rota}/{{id}}", name=f"obter_{tabela}", tags=[tabela])
    def consultar(id: Id, db: Banco):
        return s.serializar(s.obter(db, tabela, id))

    @app.put(f"{rota}/{{id}}", name=f"alterar_{tabela}", tags=[tabela])
    def atualizar(id: Id, dados: modelo, db: Banco):
        atual = s.obter(db, tabela, id)
        valores = dados.model_dump(mode="json")
        if preparar:
            preparar(db, valores, atual)
        gravar(db, tabela, valores, id)
        if tabela == "turmas":
            s.atualizar_fila(db, id, s.agora())
        return s.serializar(s.obter(db, tabela, id))

    @app.delete(f"{rota}/{{id}}", status_code=204, name=f"excluir_{tabela}", tags=[tabela])
    def excluir(id: Id, db: Banco):
        s.obter(db, tabela, id)
        db.execute(f"DELETE FROM {tabela} WHERE id = ?", (id,))
        return Response(status_code=204)


def preparar_disciplina(db, valores, atual=None):
    if atual and valores["creditos"] != atual["creditos"] and db.execute("""
        SELECT 1 FROM turmas t JOIN matriculas m ON m.turma_id = t.id
        WHERE t.disciplina_id = ? AND m.estado IN ('confirmada', 'solicitada', 'lista_de_espera')
    """, (atual["id"],)).fetchone():
        s.conflito("Creditos da disciplina vinculados a matriculas ativas")


def preparar_turma(db, valores, atual=None):
    s.obter(db, "disciplinas", valores["disciplina_id"])
    valores["horario"] = json.dumps(sorted(valores["horario"], key=lambda h: (h["dia"], h["inicio"])))
    estado = valores["estado"]
    fechado = db.execute("SELECT 1 FROM periodos_encerrados WHERE semestre = ?",
                         (valores["semestre"],)).fetchone()
    if fechado and (atual is None or estado in ("aberta", "lotada")):
        s.conflito("Periodo de matricula encerrado")
    if atual:
        turma_id = atual["id"]
        if atual["estado"] in ("cancelada", "encerrada") and estado in ("aberta", "lotada"):
            s.conflito("Turma fora do periodo de admissao")
        if atual["estado"] == "cancelada" and estado != "cancelada":
            s.conflito("Turma cancelada")
        if any(valores[campo] != atual[campo] for campo in ("disciplina_id", "semestre", "horario")):
            if db.execute("SELECT 1 FROM matriculas WHERE turma_id = ?", (turma_id,)).fetchone():
                s.conflito("Disciplina, semestre e horario vinculados a matriculas")
        if estado in ("cancelada", "encerrada"):
            s.fechar_turma(db, turma_id, estado)
        ocupadas = s.contar_ocupadas(db, turma_id)
        if valores["vagas"] < ocupadas:
            s.conflito("Capacidade inferior ao total de matriculas confirmadas e vagas reservadas")
    else:
        ocupadas = 0
    if estado in ("aberta", "lotada"):
        valores["estado"] = "lotada" if ocupadas == valores["vagas"] else "aberta"


def criar_app(caminho=None):
    caminho = Path(caminho or os.environ.get("MATRICULAS_DB", Path(__file__).with_name("matriculas.sqlite3")))

    def executar_manutencao():
        with s.transacao(caminho) as db:
            s.expirar_reservas(db, s.agora())

    async def manter_fila():
        while True:
            try:
                await run_in_threadpool(executar_manutencao)
            except sqlite3.OperationalError:
                logger.exception("Falha ao atualizar a lista de espera")
            await asyncio.sleep(15)

    @asynccontextmanager
    async def lifespan(app):
        s.inicializar(caminho)
        tarefa = asyncio.create_task(manter_fila())
        try:
            yield
        finally:
            tarefa.cancel()
            with suppress(asyncio.CancelledError):
                await tarefa

    app = FastAPI(title="Matriculas academicas", lifespan=lifespan)
    app.state.caminho = caminho

    @app.exception_handler(sqlite3.IntegrityError)
    async def erro_integridade(request, erro):
        return JSONResponse(status_code=409, content={"detail": "Registro duplicado ou com vinculos ativos"})

    criar_crud(app, "alunos", modelos.Aluno)
    criar_crud(app, "disciplinas", modelos.Disciplina, preparar_disciplina)
    criar_crud(app, "turmas", modelos.Turma, preparar_turma)

    @app.post("/matriculas", status_code=201, tags=["matriculas"])
    def solicitar(dados: modelos.Solicitacao, db: Banco):
        aluno = s.obter(db, "alunos", dados.aluno_id)
        turma = s.obter(db, "turmas", dados.turma_id)
        if turma["estado"] not in ("aberta", "lotada"):
            s.conflito("Turma indisponivel para matricula")
        s.verificar_elegibilidade(db, aluno, turma)
        instante = s.agora()
        confirmada = s.contar_ocupadas(db, turma["id"]) < turma["vagas"]
        valores = dados.model_dump()
        valores.update(data=instante.isoformat(),
                       estado="confirmada" if confirmada else "lista_de_espera",
                       confirmada_em=instante.isoformat() if confirmada else None)
        matricula = gravar(db, "matriculas", valores)
        s.atualizar_fila(db, turma["id"], instante)
        return matricula

    @app.post("/matriculas/{id}/confirmar", tags=["matriculas"])
    def confirmar(id: Id, db: Banco):
        instante = s.agora()
        matricula = s.obter(db, "matriculas", id)
        if matricula["estado"] == "confirmada":
            return s.serializar(matricula)
        if matricula["estado"] != "solicitada" or instante >= datetime.fromisoformat(matricula["prazo_confirmacao"]):
            s.conflito("Matricula sem oferta de vaga vigente")
        turma = s.obter(db, "turmas", matricula["turma_id"])
        aluno = s.obter(db, "alunos", matricula["aluno_id"])
        s.verificar_elegibilidade(db, aluno, turma)
        s.alterar_matricula(db, id, "confirmada", instante)
        return s.serializar(s.obter(db, "matriculas", id))

    @app.post("/matriculas/{id}/cancelar", tags=["matriculas"])
    def cancelar(id: Id, db: Banco):
        s.encerrar_matricula(db, s.obter(db, "matriculas", id), False, s.agora())
        return s.serializar(s.obter(db, "matriculas", id))

    @app.post("/matriculas/{id}/trancar", tags=["matriculas"])
    def trancar(id: Id, db: Banco):
        s.encerrar_matricula(db, s.obter(db, "matriculas", id), True, s.agora())
        return s.serializar(s.obter(db, "matriculas", id))

    @app.get("/alunos/{id}/matriculas", tags=["matriculas"])
    def matriculas_aluno(id: Id, db: Banco):
        s.obter(db, "alunos", id)
        return listar(db, "SELECT * FROM matriculas WHERE aluno_id = ? ORDER BY data, id", id)

    @app.get("/turmas/{id}/lista-de-espera", tags=["matriculas"])
    def consultar_fila(id: Id, db: Banco):
        s.obter(db, "turmas", id)
        return {
            "ofertas": [dict(linha) for linha in s.fila(db, id, "solicitada")],
            "fila": [dict(linha) for linha in s.fila(db, id)],
        }

    @app.post("/periodos-matricula/{semestre}/encerrar", tags=["matriculas"])
    def encerrar_periodo(semestre: modelos.Semestre, db: Banco):
        inserido = db.execute("INSERT OR IGNORE INTO periodos_encerrados VALUES (?)", (semestre,))
        if inserido.rowcount:
            turmas = db.execute("""
                SELECT t.id, COUNT(m.id) AS confirmadas FROM turmas t
                LEFT JOIN matriculas m ON m.turma_id = t.id AND m.estado = 'confirmada'
                WHERE t.semestre = ? AND t.estado <> 'cancelada' GROUP BY t.id
            """, (semestre,)).fetchall()
            for turma in turmas:
                s.fechar_turma(db, turma["id"], "cancelada" if turma["confirmadas"] < 5 else "encerrada")
        return listar(db, "SELECT * FROM turmas WHERE semestre = ? ORDER BY id", semestre)

    @app.get("/disciplinas/{id}/pre-requisitos", tags=["pre-requisitos"])
    def pre_requisitos(id: Id, db: Banco):
        s.obter(db, "disciplinas", id)
        return listar(db, """
            SELECT d.* FROM disciplinas d JOIN pre_requisitos p ON d.id = p.exigida_id
            WHERE p.disciplina_id = ? ORDER BY d.codigo
        """, id)

    @app.post("/disciplinas/{id}/pre-requisitos", status_code=201, tags=["pre-requisitos"])
    def adicionar_pre_requisito(id: Id, dados: modelos.PreRequisito, db: Banco):
        s.obter(db, "disciplinas", id)
        s.obter(db, "disciplinas", dados.exigida_id)
        ciclo = db.execute("""
            WITH RECURSIVE exigencias(id) AS (
                SELECT ? UNION SELECT p.exigida_id FROM pre_requisitos p
                JOIN exigencias e ON p.disciplina_id = e.id
            )
            SELECT 1 FROM exigencias WHERE id = ?
        """, (dados.exigida_id, id)).fetchone()
        if ciclo:
            s.conflito("Pre-requisito formaria um ciclo")
        db.execute("INSERT INTO pre_requisitos VALUES (?, ?)", (id, dados.exigida_id))
        return {"disciplina_id": id, "exigida_id": dados.exigida_id}

    @app.delete("/disciplinas/{id}/pre-requisitos/{exigida_id}", status_code=204, tags=["pre-requisitos"])
    def remover_pre_requisito(id: Id, exigida_id: Id, db: Banco):
        resultado = db.execute("DELETE FROM pre_requisitos WHERE disciplina_id = ? AND exigida_id = ?",
                               (id, exigida_id))
        if not resultado.rowcount:
            raise HTTPException(404, "Pre-requisito inexistente")
        return Response(status_code=204)

    @app.get("/alunos/{id}/historico", tags=["historico"])
    def consultar_historico(id: Id, db: Banco):
        s.obter(db, "alunos", id)
        return listar(db, "SELECT * FROM historico WHERE aluno_id = ? ORDER BY semestre, id", id)

    @app.post("/alunos/{id}/historico", status_code=201, tags=["historico"])
    def inserir_historico(id: Id, dados: modelos.Historico, db: Banco):
        s.obter(db, "alunos", id)
        s.obter(db, "disciplinas", dados.disciplina_id)
        registro = gravar(db, "historico", {"aluno_id": id, **dados.model_dump(mode="json")})
        if dados.situacao == modelos.SituacaoHistorico.TRANCADO:
            instante = s.agora()
            for turma_id in sorted(s.aplicar_trancamento_do_aluno(db, id, dados.semestre)):
                s.atualizar_fila(db, turma_id, instante)
        return registro

    @app.get("/relatorios/disciplinas-mais-procuradas", tags=["relatorios"])
    def demanda(semestre: Annotated[modelos.Semestre, Query()], db: Banco):
        return listar(db, """
            SELECT d.id AS disciplina_id, d.codigo, d.nome, COUNT(m.id) AS solicitacoes
            FROM matriculas m JOIN turmas t ON t.id = m.turma_id JOIN disciplinas d ON d.id = t.disciplina_id
            WHERE t.semestre = ? GROUP BY d.id ORDER BY solicitacoes DESC, d.codigo
        """, semestre)

    @app.get("/relatorios/taxa-reprovacao", tags=["relatorios"])
    def reprovacao(db: Banco, semestre: modelos.Semestre | None = None):
        return listar(db, """
            SELECT d.id AS disciplina_id, d.codigo, d.nome, COUNT(h.id) AS resultados,
                   COUNT(CASE WHEN h.situacao = 'reprovado' THEN 1 END) AS reprovacoes,
                   100.0 * COUNT(CASE WHEN h.situacao = 'reprovado' THEN 1 END)
                   / NULLIF(COUNT(h.id), 0) AS taxa_percentual
            FROM disciplinas d LEFT JOIN historico h ON h.disciplina_id = d.id
                AND h.situacao IN ('aprovado', 'reprovado') AND (? IS NULL OR h.semestre = ?)
            GROUP BY d.id ORDER BY d.codigo
        """, semestre, semestre)

    @app.get("/relatorios/ocupacao", tags=["relatorios"])
    def ocupacao(db: Banco, semestre: modelos.Semestre | None = None):
        return listar(db, """
            WITH ocupadas AS (
                SELECT turma_id, COUNT(*) AS confirmadas FROM matriculas
                WHERE estado = 'confirmada' GROUP BY turma_id
            )
            SELECT d.departamento, COUNT(*) AS turmas, SUM(t.vagas) AS vagas,
                   SUM(COALESCE(o.confirmadas, 0)) AS confirmadas,
                   100.0 * SUM(COALESCE(o.confirmadas, 0)) / SUM(t.vagas) AS ocupacao_percentual
            FROM turmas t JOIN disciplinas d ON d.id = t.disciplina_id
            LEFT JOIN ocupadas o ON o.turma_id = t.id
            WHERE t.estado <> 'cancelada' AND (? IS NULL OR t.semestre = ?)
            GROUP BY d.departamento ORDER BY d.departamento
        """, semestre, semestre)

    return app


app = criar_app()
