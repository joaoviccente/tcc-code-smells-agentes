import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, HTTPException, Response

import modelos
import servico
from banco import atualizar, buscar, inicializar, inserir, transacao


async def monitorar_ofertas():
    while True:
        try:
            await asyncio.to_thread(servico.expirar_ofertas)
        except sqlite3.OperationalError:
            logging.getLogger(__name__).exception("Falha ao revisar ofertas de vaga.")
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(app):
    inicializar()
    tarefa = asyncio.create_task(monitorar_ofertas())
    try:
        yield
    finally:
        tarefa.cancel()
        with suppress(asyncio.CancelledError):
            await tarefa


app = FastAPI(title="Matrículas Acadêmicas", lifespan=lifespan)


def formatar(tabela, item):
    item = dict(item)
    if tabela == "turmas":
        item["horario"] = {campo: item.pop(campo) for campo in ("dia_semana", "inicio", "fim")}
        item["periodo_encerrado"] = bool(item["periodo_encerrado"])
    return item


def salvar(db, tabela, dados, id=None):
    anterior = buscar(db, tabela, id) if id is not None else None
    valores = dados.model_dump()
    if tabela == "disciplinas" and anterior and anterior["creditos"] != dados.creditos:
        if db.execute("""
            SELECT 1 FROM matriculas m JOIN turmas t ON t.id = m.turma_id
            WHERE t.disciplina_id = ? AND m.estado = 'confirmada' LIMIT 1
        """, (id,)).fetchone():
            raise HTTPException(409, "A disciplina possui matriculas confirmadas.")
    if tabela == "alunos" and anterior and anterior["categoria"] != dados.categoria:
        if db.execute("""
            SELECT 1 FROM matriculas WHERE aluno_id = ? AND estado = 'confirmada' LIMIT 1
        """, (id,)).fetchone():
            raise HTTPException(409, "O aluno possui matriculas confirmadas.")
    if tabela == "turmas":
        buscar(db, "disciplinas", dados.disciplina_id)
        valores.pop("horario")
        valores.update(dados.horario.model_dump(mode="json"))
        if anterior:
            if anterior["estado"] in ("cancelada", "encerrada") and dados.estado != anterior["estado"]:
                raise HTTPException(409, "O estado final da turma nao pode ser revertido.")
            campos = ("disciplina_id", "semestre", "dia_semana", "inicio", "fim")
            if any(anterior[campo] != valores[campo] for campo in campos) and db.execute(
                "SELECT 1 FROM matriculas WHERE turma_id = ? LIMIT 1", (id,)
            ).fetchone():
                raise HTTPException(409, "A turma possui registros de matricula.")
            if dados.estado not in ("cancelada", "encerrada") and dados.vagas < servico.ocupadas(db, id):
                raise HTTPException(409, "Ja existem mais vagas ocupadas do que a capacidade informada.")
        if dados.estado == "encerrada":
            if anterior and not anterior["periodo_encerrado"]:
                servico.fechar_periodo(db, id)
                if buscar(db, tabela, id)["estado"] == "cancelada":
                    valores["estado"] = "cancelada"
            if anterior is None:
                valores["estado"] = "cancelada"
            valores["periodo_encerrado"] = 1
    if anterior is None:
        id = inserir(db, tabela, valores)
    else:
        atualizar(db, tabela, id, valores)
    if tabela == "turmas":
        if valores["estado"] == "cancelada":
            servico.cancelar_turma(db, id)
        elif dados.estado == "encerrada":
            db.execute("""
                UPDATE matriculas SET estado = 'cancelada', prazo_confirmacao = NULL
                WHERE turma_id = ? AND estado IN ('solicitada', 'lista_de_espera')
            """, (id,))
        else:
            servico.distribuir_vagas(db, id, servico.agora())
    return formatar(tabela, buscar(db, tabela, id))


def registrar_crud(tabela, modelo):
    rota = f"/{tabela}"

    def criar(dados: modelo):
        with transacao() as db:
            return salvar(db, tabela, dados)

    def listar():
        with transacao(escrita=False) as db:
            return [formatar(tabela, linha) for linha in db.execute(f"SELECT * FROM {tabela} ORDER BY id")]

    def consultar(id: int):
        with transacao(escrita=False) as db:
            return formatar(tabela, buscar(db, tabela, id))

    def substituir(id: int, dados: modelo):
        with transacao() as db:
            return salvar(db, tabela, dados, id)

    def excluir(id: int):
        with transacao() as db:
            buscar(db, tabela, id)
            db.execute(f"DELETE FROM {tabela} WHERE id = ?", (id,))
        return Response(status_code=204)

    app.add_api_route(rota, criar, methods=["POST"], status_code=201, name=f"criar_{tabela}")
    app.add_api_route(rota, listar, methods=["GET"], name=f"listar_{tabela}")
    app.add_api_route(rota + "/{id}", consultar, methods=["GET"], name=f"consultar_{tabela}")
    app.add_api_route(rota + "/{id}", substituir, methods=["PUT"], name=f"substituir_{tabela}")
    app.add_api_route(rota + "/{id}", excluir, methods=["DELETE"], status_code=204, name=f"excluir_{tabela}")


registrar_crud("alunos", modelos.Aluno)
registrar_crud("disciplinas", modelos.Disciplina)
registrar_crud("turmas", modelos.Turma)


@app.post("/disciplinas/{id}/pre-requisitos", status_code=201)
def adicionar_pre_requisito(id: int, dados: modelos.PreRequisito):
    with transacao() as db:
        buscar(db, "disciplinas", id)
        buscar(db, "disciplinas", dados.exigida_id)
        ciclo = db.execute("""
            WITH RECURSIVE exigencias(id) AS (
                SELECT ? UNION
                SELECT p.exigida_id FROM pre_requisitos p JOIN exigencias e ON p.disciplina_id = e.id
            )
            SELECT 1 FROM exigencias WHERE id = ?
        """, (dados.exigida_id, id)).fetchone()
        if ciclo:
            raise HTTPException(409, "Pre-requisito criaria uma dependencia circular.")
        registro = {"disciplina_id": id, "exigida_id": dados.exigida_id}
        inserir(db, "pre_requisitos", registro)
        return registro


@app.get("/disciplinas/{id}/pre-requisitos")
def listar_pre_requisitos(id: int):
    with transacao(escrita=False) as db:
        buscar(db, "disciplinas", id)
        return [dict(item) for item in db.execute(
            "SELECT * FROM pre_requisitos WHERE disciplina_id = ? ORDER BY exigida_id", (id,)
        )]


@app.post("/alunos/{id}/historico", status_code=201)
def registrar_historico(id: int, dados: modelos.Historico):
    with transacao() as db:
        buscar(db, "alunos", id)
        buscar(db, "disciplinas", dados.disciplina_id)
        historico_id = inserir(db, "historico", {"aluno_id": id, **dados.model_dump()})
        if dados.situacao == "trancado":
            instante = servico.agora()
            for turma_id in sorted(servico.aplicar_trancamento_do_aluno(db, id, dados.semestre)):
                servico.distribuir_vagas(db, turma_id, instante)
        return buscar(db, "historico", historico_id)


@app.get("/alunos/{id}/historico")
def consultar_historico(id: int):
    with transacao(escrita=False) as db:
        buscar(db, "alunos", id)
        return [dict(item) for item in db.execute(
            "SELECT * FROM historico WHERE aluno_id = ? ORDER BY semestre, id", (id,)
        )]


@app.post("/matriculas", status_code=201, dependencies=[Depends(servico.expirar_ofertas)])
def solicitar_matricula(dados: modelos.Solicitacao):
    with transacao() as db:
        return servico.solicitar(db, dados)


@app.post("/matriculas/{id}/confirmar", dependencies=[Depends(servico.expirar_ofertas)])
def confirmar_matricula(id: int):
    with transacao() as db:
        return servico.confirmar(db, id)


@app.post("/matriculas/{id}/cancelar", dependencies=[Depends(servico.expirar_ofertas)])
def cancelar_matricula(id: int):
    with transacao() as db:
        return servico.desfazer(db, id)


@app.post("/matriculas/{id}/trancar", dependencies=[Depends(servico.expirar_ofertas)])
def trancar_matricula(id: int):
    with transacao() as db:
        return servico.desfazer(db, id, trancar=True)


@app.get("/alunos/{id}/matriculas", dependencies=[Depends(servico.expirar_ofertas)])
def listar_matriculas(id: int):
    with transacao(escrita=False) as db:
        buscar(db, "alunos", id)
        return [dict(item) for item in db.execute(
            "SELECT * FROM matriculas WHERE aluno_id = ? ORDER BY data, id", (id,)
        )]


@app.get("/turmas/{id}/lista-de-espera", dependencies=[Depends(servico.expirar_ofertas)])
def consultar_fila(id: int):
    with transacao(escrita=False) as db:
        buscar(db, "turmas", id)
        ofertas = db.execute("""
            SELECT m.*, a.categoria FROM matriculas m JOIN alunos a ON a.id = m.aluno_id
            WHERE m.turma_id = ? AND m.estado = 'solicitada' AND m.prazo_confirmacao IS NOT NULL
            ORDER BY m.prazo_confirmacao, m.id
        """, (id,))
        return {"fila": [dict(item) for item in servico.fila(db, id)],
                "ofertas": [dict(item) for item in ofertas]}


@app.post("/turmas/{id}/encerrar-periodo-matricula")
def encerrar_periodo(id: int):
    with transacao() as db:
        servico.fechar_periodo(db, id)
        return formatar("turmas", buscar(db, "turmas", id))


@app.get("/relatorios/disciplinas-mais-procuradas")
def disciplinas_mais_procuradas(semestre: modelos.Semestre):
    with transacao(escrita=False) as db:
        return [dict(item) for item in db.execute("""
            SELECT d.id AS disciplina_id, d.codigo, d.nome, COUNT(m.id) AS solicitacoes
            FROM disciplinas d JOIN turmas t ON t.disciplina_id = d.id
            JOIN matriculas m ON m.turma_id = t.id
            WHERE t.semestre = ? GROUP BY d.id ORDER BY solicitacoes DESC, d.codigo
        """, (semestre,))]


@app.get("/relatorios/taxa-reprovacao")
def taxa_reprovacao(semestre: modelos.Semestre | None = None):
    with transacao(escrita=False) as db:
        return [dict(item) for item in db.execute("""
            SELECT d.id AS disciplina_id, d.codigo, d.nome, COUNT(h.id) AS resultados,
                   COUNT(CASE WHEN h.situacao = 'reprovado' THEN 1 END) AS reprovacoes,
                   100.0 * COUNT(CASE WHEN h.situacao = 'reprovado' THEN 1 END)
                        / NULLIF(COUNT(h.id), 0) AS taxa_percentual
            FROM disciplinas d LEFT JOIN historico h ON h.disciplina_id = d.id
                AND h.situacao IN ('aprovado', 'reprovado') AND (? IS NULL OR h.semestre = ?)
            GROUP BY d.id ORDER BY d.codigo
        """, (semestre, semestre))]


@app.get("/relatorios/ocupacao-turmas")
def ocupacao_turmas(semestre: modelos.Semestre | None = None):
    with transacao(escrita=False) as db:
        return [dict(item) for item in db.execute("""
            WITH ocupacao AS (
                SELECT t.id, d.departamento, t.vagas, COUNT(m.id) AS confirmadas
                FROM turmas t JOIN disciplinas d ON t.disciplina_id = d.id
                LEFT JOIN matriculas m ON m.turma_id = t.id AND m.estado = 'confirmada'
                WHERE t.estado <> 'cancelada' AND (? IS NULL OR t.semestre = ?)
                GROUP BY t.id
            )
            SELECT departamento, COUNT(*) AS turmas, SUM(vagas) AS vagas,
                   SUM(confirmadas) AS confirmadas,
                   100.0 * SUM(confirmadas) / SUM(vagas) AS ocupacao_percentual
            FROM ocupacao GROUP BY departamento ORDER BY departamento
        """, (semestre, semestre))]
