import asyncio
import json
import logging
import sqlite3
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from banco import conexao, inicializar, transacao
from matriculas import (agora, atualizar_fila, cancelar_turma, confirmar, erro,
                        expirar_ofertas, fila, obter, quantidade, retirar, solicitar)
from modelos import Aluno, Disciplina, Historico, Id, PreRequisito, Semestre, Solicitacao, Turma

logger = logging.getLogger(__name__)


async def processar_fila():
    while True:
        try:
            await asyncio.to_thread(expirar_ofertas)
        except sqlite3.Error:
            logger.exception("Falha ao processar a lista de espera")
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(inicializar)
    tarefa = asyncio.create_task(processar_fila())
    try:
        yield
    finally:
        tarefa.cancel()
        with suppress(asyncio.CancelledError):
            await tarefa


app = FastAPI(title="Matrículas Acadêmicas", lifespan=lifespan)


@app.exception_handler(sqlite3.IntegrityError)
async def conflito_integridade(request, exc):
    mensagens = {
        "SQLITE_CONSTRAINT_FOREIGNKEY": "Operação conflita com registros relacionados",
        "SQLITE_CONSTRAINT_UNIQUE": "Já existe um registro com esse identificador",
        "SQLITE_CONSTRAINT_PRIMARYKEY": "Já existe um registro com esse identificador",
    }
    return JSONResponse(status_code=409, content={"detail": mensagens.get(
        exc.sqlite_errorname, "Operação viola uma restrição do banco")})


def serializar(linha):
    item = dict(linha)
    if "horario" in item:
        item["horario"] = json.loads(item["horario"])
    return item


def gravar(db, tabela, dados, id=None):
    if "horario" in dados:
        dados["horario"] = json.dumps(dados["horario"])
    if id is None:
        colunas = ", ".join(dados)
        marcadores = ", ".join("?" for _ in dados)
        return db.execute(f"INSERT INTO {tabela} ({colunas}) VALUES ({marcadores})",
                          tuple(dados.values())).lastrowid
    atribuicoes = ", ".join(f"{coluna} = ?" for coluna in dados)
    db.execute(f"UPDATE {tabela} SET {atribuicoes} WHERE id = ?", (*dados.values(), id))
    return id


def salvar_turma(db, dados, id):
    obter(db, "disciplinas", dados["disciplina_id"])
    estado = dados["estado"]
    if id is not None:
        anterior = obter(db, "turmas", id)
        if anterior["estado"] in ("cancelada", "encerrada") and estado != anterior["estado"]:
            erro(409, "Turma finalizada não pode mudar de estado")
        if quantidade(db, "SELECT count(*) FROM matriculas WHERE turma_id = ?", (id,)):
            campos_fixos = ("disciplina_id", "semestre", "horario")
            if any(serializar(anterior)[campo] != dados[campo] for campo in campos_fixos):
                erro(409, "Disciplina, semestre e horário são fixos após a primeira matrícula")
        reservadas = quantidade(db, """
            SELECT count(*) FROM matriculas WHERE turma_id = ?
            AND (estado = 'confirmada' OR oferta_expira_em IS NOT NULL)
        """, (id,))
        if estado in ("aberta", "lotada") and dados["vagas"] < reservadas:
            erro(409, "Total de vagas é inferior ao número de vagas ocupadas e reservadas")
    id = gravar(db, "turmas", dados, id)
    if estado == "cancelada":
        cancelar_turma(db, id)
    elif estado == "encerrada":
        db.execute("""
            UPDATE matriculas SET estado = 'cancelada', oferta_expira_em = NULL
            WHERE turma_id = ? AND estado IN ('solicitada', 'lista_de_espera')
        """, (id,))
    else:
        atualizar_fila(db, id, agora())
    return id


def registrar_crud(tabela, modelo):
    def salvar(dados, id=None):
        if tabela == "turmas":
            expirar_ofertas()
        with transacao() as db:
            valores = dados.model_dump(mode="json")
            anterior = obter(db, tabela, id) if id is not None else None
            if tabela == "disciplinas" and anterior and anterior["creditos"] != valores["creditos"]:
                if quantidade(db, """
                    SELECT count(*) FROM matriculas m JOIN turmas t ON t.id = m.turma_id
                    WHERE t.disciplina_id = ? AND m.estado = 'confirmada'
                """, (id,)):
                    erro(409, "Créditos são fixos enquanto houver matrículas confirmadas")
            if tabela == "alunos" and anterior and anterior["categoria"] != valores["categoria"]:
                if quantidade(db, """
                    SELECT count(*) FROM matriculas WHERE aluno_id = ?
                    AND estado IN ('confirmada', 'lista_de_espera', 'solicitada')
                """, (id,)):
                    erro(409, "Categoria é fixa enquanto houver matrículas vigentes")
            registro_id = (salvar_turma(db, valores, id) if tabela == "turmas"
                           else gravar(db, tabela, valores, id))
            return serializar(obter(db, tabela, registro_id))

    def criar(dados: modelo):
        return salvar(dados)

    def listar():
        if tabela == "turmas":
            expirar_ofertas()
        with conexao() as db:
            return [serializar(item) for item in db.execute(f"SELECT * FROM {tabela} ORDER BY id")]

    def consultar(id: Id):
        if tabela == "turmas":
            expirar_ofertas()
        with conexao() as db:
            return serializar(obter(db, tabela, id))

    def atualizar(id: Id, dados: modelo):
        return salvar(dados, id)

    def excluir(id: Id):
        with transacao() as db:
            obter(db, tabela, id)
            db.execute(f"DELETE FROM {tabela} WHERE id = ?", (id,))
        return Response(status_code=204)

    rotas = (
        ("", criar, "POST", 201), ("", listar, "GET", 200),
        ("/{id}", consultar, "GET", 200), ("/{id}", atualizar, "PUT", 200),
        ("/{id}", excluir, "DELETE", 204),
    )
    for sufixo, funcao, metodo, status in rotas:
        app.add_api_route(f"/{tabela}{sufixo}", funcao, methods=[metodo], status_code=status,
                          name=f"{funcao.__name__}_{tabela}", tags=[tabela])


registrar_crud("alunos", Aluno)
registrar_crud("disciplinas", Disciplina)
registrar_crud("turmas", Turma)


@app.post("/disciplinas/{id}/pre-requisitos", status_code=201)
def adicionar_pre_requisito(id: Id, dados: PreRequisito):
    exigida = dados.disciplina_exigida_id
    with transacao() as db:
        obter(db, "disciplinas", id)
        obter(db, "disciplinas", exigida)
        if quantidade(db, """
            WITH RECURSIVE exigencias(id) AS (
                SELECT ? UNION SELECT p.disciplina_exigida_id
                FROM prerequisitos p JOIN exigencias e ON p.disciplina_id = e.id
            ) SELECT count(*) FROM exigencias WHERE id = ?
        """, (exigida, id)):
            erro(409, "Pré-requisito criaria uma dependência circular")
        db.execute("INSERT INTO prerequisitos VALUES (?, ?)", (id, exigida))
    return {"disciplina_id": id, "disciplina_exigida_id": exigida}


@app.get("/disciplinas/{id}/pre-requisitos")
def listar_pre_requisitos(id: Id):
    with conexao() as db:
        obter(db, "disciplinas", id)
        return [dict(item) for item in db.execute("""
            SELECT * FROM prerequisitos WHERE disciplina_id = ? ORDER BY disciplina_exigida_id
        """, (id,))]


@app.delete("/disciplinas/{id}/pre-requisitos/{exigida}", status_code=204)
def excluir_pre_requisito(id: Id, exigida: Id):
    with transacao() as db:
        cursor = db.execute("DELETE FROM prerequisitos WHERE disciplina_id = ? AND disciplina_exigida_id = ?",
                            (id, exigida))
        if not cursor.rowcount:
            erro(404, "Pré-requisito não encontrado")
    return Response(status_code=204)


@app.post("/matriculas", status_code=201)
def criar_matricula(dados: Solicitacao):
    expirar_ofertas()
    with transacao() as db:
        return dict(solicitar(db, dados.aluno_id, dados.turma_id, agora()))


def alterar_matricula(id, acao):
    expirar_ofertas()
    with transacao() as db:
        matricula = obter(db, "matriculas", id)
        return dict(acao(db, matricula, agora()))


@app.post("/matriculas/{id}/confirmar")
def confirmar_matricula(id: Id):
    return alterar_matricula(id, confirmar)


@app.post("/matriculas/{id}/cancelar")
def cancelar_matricula(id: Id):
    return alterar_matricula(id, lambda db, matricula, instante: retirar(db, matricula, instante, trancar=False))


@app.post("/matriculas/{id}/trancar")
def trancar_matricula(id: Id):
    return alterar_matricula(id, lambda db, matricula, instante: retirar(db, matricula, instante, trancar=True))


@app.get("/alunos/{id}/matriculas")
def listar_matriculas(id: Id):
    expirar_ofertas()
    with conexao() as db:
        obter(db, "alunos", id)
        return [dict(item) for item in db.execute("SELECT * FROM matriculas WHERE aluno_id = ? ORDER BY id", (id,))]


@app.get("/turmas/{id}/lista-de-espera")
def consultar_fila(id: Id):
    expirar_ofertas()
    with conexao() as db:
        obter(db, "turmas", id)
        return [dict(item) for item in fila(db, id)]


@app.post("/alunos/{id}/historico", status_code=201)
def registrar_historico(id: Id, dados: Historico):
    with transacao() as db:
        obter(db, "alunos", id)
        obter(db, "disciplinas", dados.disciplina_id)
        registro = gravar(db, "historico", {"aluno_id": id, **dados.model_dump()})
        return dict(obter(db, "historico", registro))


@app.get("/alunos/{id}/historico")
def consultar_historico(id: Id):
    with conexao() as db:
        obter(db, "alunos", id)
        return [dict(item) for item in db.execute(
            "SELECT * FROM historico WHERE aluno_id = ? ORDER BY semestre, id", (id,))]


@app.post("/semestres/{semestre}/encerrar-matriculas")
def encerrar_matriculas(semestre: Semestre):
    with transacao() as db:
        if not quantidade(db, "SELECT count(*) FROM turmas WHERE semestre = ?", (semestre,)):
            erro(404, "Semestre sem turmas cadastradas")
        primeira_execucao = db.execute("INSERT OR IGNORE INTO periodos_encerrados VALUES (?)", (semestre,)).rowcount
        canceladas = []
        if primeira_execucao:
            for turma in db.execute("""
                SELECT t.id FROM turmas t LEFT JOIN matriculas m
                ON m.turma_id = t.id AND m.estado = 'confirmada'
                WHERE t.semestre = ? AND t.estado <> 'cancelada'
                GROUP BY t.id HAVING count(m.id) < 5 ORDER BY t.id
            """, (semestre,)).fetchall():
                cancelar_turma(db, turma["id"])
                canceladas.append(turma["id"])
        return {"semestre": semestre, "turmas_canceladas": canceladas}


@app.get("/relatorios/disciplinas-mais-procuradas")
def disciplinas_mais_procuradas(semestre: Semestre):
    with conexao() as db:
        return [dict(item) for item in db.execute("""
            SELECT d.id AS disciplina_id, d.codigo, d.nome, count(m.id) AS solicitacoes
            FROM disciplinas d JOIN turmas t ON t.disciplina_id = d.id
            JOIN matriculas m ON m.turma_id = t.id WHERE t.semestre = ?
            GROUP BY d.id ORDER BY solicitacoes DESC, d.codigo
        """, (semestre,))]


@app.get("/relatorios/taxa-reprovacao")
def taxa_reprovacao(semestre: Semestre | None = None):
    with conexao() as db:
        return [dict(item) for item in db.execute("""
            SELECT d.id AS disciplina_id, d.codigo, d.nome,
                count(h.id) AS avaliacoes,
                count(CASE WHEN h.situacao = 'reprovado' THEN 1 END) AS reprovacoes,
                1.0 * count(CASE WHEN h.situacao = 'reprovado' THEN 1 END) /
                    nullif(count(h.id), 0) AS taxa_reprovacao
            FROM disciplinas d LEFT JOIN historico h ON h.disciplina_id = d.id
                AND h.situacao IN ('aprovado', 'reprovado') AND (? IS NULL OR h.semestre = ?)
            GROUP BY d.id ORDER BY d.codigo
        """, (semestre, semestre))]


@app.get("/relatorios/ocupacao-turmas")
def ocupacao_turmas(semestre: Semestre | None = None, departamento: str | None = None):
    with conexao() as db:
        departamentos = {}
        for item in db.execute("""
            SELECT d.departamento, t.id AS turma_id, d.codigo, t.semestre, t.vagas,
                count(m.id) AS confirmadas, 1.0 * count(m.id) / t.vagas AS taxa_ocupacao
            FROM turmas t JOIN disciplinas d ON d.id = t.disciplina_id
            LEFT JOIN matriculas m ON m.turma_id = t.id AND m.estado = 'confirmada'
            WHERE (? IS NULL OR t.semestre = ?) AND (? IS NULL OR d.departamento = ?)
            GROUP BY t.id ORDER BY d.departamento, t.id
        """, (semestre, semestre, departamento, departamento)):
            turma = dict(item)
            departamentos.setdefault(turma.pop("departamento"), []).append(turma)
        return [{"departamento": nome, "turmas": turmas} for nome, turmas in departamentos.items()]
