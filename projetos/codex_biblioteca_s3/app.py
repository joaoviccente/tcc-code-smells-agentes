from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import os
import sqlite3
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="Biblioteca universitária")
REGRAS = {
    "aluno": (3, 7, 2, 100, 3000),
    "professor": (8, 30, 4, 50, 5000),
    "visitante": (1, 3, 0, 200, 2000),
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
 id INTEGER PRIMARY KEY, nome TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
 matricula TEXT NOT NULL UNIQUE, categoria TEXT NOT NULL, situacao TEXT NOT NULL, suspenso_ate TEXT);
CREATE TABLE IF NOT EXISTS livros (
 id INTEGER PRIMARY KEY, titulo TEXT NOT NULL, autor TEXT NOT NULL,
 isbn TEXT NOT NULL UNIQUE, ano INTEGER NOT NULL, area_conhecimento TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exemplares (
 id INTEGER PRIMARY KEY, livro_id INTEGER NOT NULL REFERENCES livros(id),
 codigo_tombo TEXT NOT NULL UNIQUE, estado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS emprestimos (
 id INTEGER PRIMARY KEY, exemplar_id INTEGER NOT NULL REFERENCES exemplares(id),
 usuario_id INTEGER NOT NULL REFERENCES usuarios(id), categoria TEXT NOT NULL,
 data_retirada TEXT NOT NULL, data_prevista TEXT NOT NULL, data_devolucao TEXT,
 estado TEXT NOT NULL, numero_renovacoes INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS emprestimo_em_curso
 ON emprestimos(exemplar_id) WHERE data_devolucao IS NULL;
CREATE TABLE IF NOT EXISTS reservas (
 id INTEGER PRIMARY KEY, livro_id INTEGER NOT NULL REFERENCES livros(id),
 usuario_id INTEGER NOT NULL REFERENCES usuarios(id), data TEXT NOT NULL,
 estado TEXT NOT NULL, exemplar_id INTEGER REFERENCES exemplares(id),
 disponivel_ate TEXT, atendida_em TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS reserva_em_curso ON reservas(livro_id, usuario_id)
 WHERE atendida_em IS NULL AND estado IN ('aguardando', 'disponivel');
CREATE TABLE IF NOT EXISTS multas (
 id INTEGER PRIMARY KEY, emprestimo_id INTEGER NOT NULL UNIQUE REFERENCES emprestimos(id),
 centavos INTEGER NOT NULL, estado TEXT NOT NULL);
"""


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Usuario(Entrada):
    nome: str = Field(min_length=1, max_length=200)
    email: str = Field(max_length=254, pattern=r"^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$")
    matricula: str = Field(min_length=1, max_length=100)
    categoria: Literal["aluno", "professor", "visitante"]
    situacao: Literal["ativo", "suspenso"] = "ativo"


class Livro(Entrada):
    titulo: str = Field(min_length=1, max_length=300)
    autor: str = Field(min_length=1, max_length=200)
    isbn: str = Field(pattern=r"^(?:[0-9]{9}[0-9X]|97[89][0-9]{10})$")
    ano: int = Field(ge=1, le=9999)
    area_conhecimento: str = Field(min_length=1, max_length=150)


class Exemplar(Entrada):
    livro_id: int = Field(gt=0)
    codigo_tombo: str = Field(min_length=1, max_length=100)
    estado: Literal["disponivel", "emprestado", "reservado", "em_reparo", "baixado"] = "disponivel"


class NovoEmprestimo(Entrada):
    exemplar_id: int = Field(gt=0)
    usuario_id: int = Field(gt=0)


class NovaReserva(Entrada):
    livro_id: int = Field(gt=0)
    usuario_id: int = Field(gt=0)


def agora():
    return datetime.now(timezone.utc)


def erro(codigo, mensagem):
    raise HTTPException(codigo, mensagem)


def linhas(db, sql, args=()):
    return [dict(row) for row in db.execute(sql, args)]


def obter(db, tabela, id):
    row = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id,)).fetchone()
    if row is None:
        erro(404, "Registro não encontrado")
    return dict(row)


def gravar(db, tabela, dados, id=None):
    if id is None:
        campos = ", ".join(dados)
        marcadores = ", ".join("?" for _ in dados)
        id = db.execute(
            f"INSERT INTO {tabela} ({campos}) VALUES ({marcadores})", tuple(dados.values())
        ).lastrowid
    else:
        campos = ", ".join(f"{campo} = ?" for campo in dados)
        db.execute(f"UPDATE {tabela} SET {campos} WHERE id = ?", (*dados.values(), id))
    return obter(db, tabela, id)


def dias_atraso(emprestimo, hoje):
    return max(0, (hoje - date.fromisoformat(emprestimo["data_prevista"])).days)


def atualizar_atraso(db, emprestimo, hoje, devolvendo=False):
    dias = dias_atraso(emprestimo, hoje)
    if not dias:
        return
    if not devolvendo:
        db.execute("UPDATE emprestimos SET estado = 'atrasado' WHERE id = ?", (emprestimo["id"],))
    if dias > 15:
        fim = (hoje + timedelta(days=dias * 2)).isoformat()
        db.execute(
            "UPDATE usuarios SET suspenso_ate = MAX(COALESCE(suspenso_ate, ''), ?) WHERE id = ?",
            (fim, emprestimo["usuario_id"]),
        )
    _, _, _, diaria, teto = REGRAS[emprestimo["categoria"]]
    perdoada = emprestimo["categoria"] == "professor" and dias <= 2
    valor = teto if devolvendo and dias > 60 else min(dias * diaria, teto)
    db.execute(
        """INSERT INTO multas (emprestimo_id, centavos, estado) VALUES (?, ?, ?)
           ON CONFLICT(emprestimo_id) DO UPDATE SET centavos = excluded.centavos,
           estado = excluded.estado""",
        (emprestimo["id"], valor, "perdoada" if perdoada else "aberta"),
    )


def distribuir(db, livro_id, instante):
    exemplares = linhas(db, """SELECT id FROM exemplares WHERE livro_id = ?
                              AND estado = 'disponivel' ORDER BY id""", (livro_id,))
    fila = linhas(db, """SELECT id FROM reservas WHERE livro_id = ?
                        AND estado = 'aguardando' ORDER BY id""", (livro_id,))
    prazo = (instante + timedelta(hours=48)).isoformat()
    for exemplar, reserva in zip(exemplares, fila):
        db.execute("UPDATE exemplares SET estado = 'reservado' WHERE id = ?", (exemplar["id"],))
        db.execute(
            """UPDATE reservas SET estado = 'disponivel', exemplar_id = ?, disponivel_ate = ?
               WHERE id = ?""",
            (exemplar["id"], prazo, reserva["id"]),
        )


def liberar(db, reserva, estado):
    db.execute("UPDATE reservas SET estado = ?, exemplar_id = NULL WHERE id = ?", (estado, reserva["id"]))
    if reserva["exemplar_id"] is not None:
        db.execute("UPDATE exemplares SET estado = 'disponivel' WHERE id = ?", (reserva["exemplar_id"],))


def sincronizar(db, instante):
    while True:
        primeira = db.execute(
            """SELECT livro_id, disponivel_ate FROM reservas WHERE estado = 'disponivel'
               AND atendida_em IS NULL AND disponivel_ate <= ? ORDER BY disponivel_ate, id LIMIT 1""",
            (instante.isoformat(),),
        ).fetchone()
        if primeira is None:
            break
        livro_id, prazo = primeira
        for reserva in linhas(db, """SELECT * FROM reservas WHERE livro_id = ? AND disponivel_ate = ?
                                    AND estado = 'disponivel' AND atendida_em IS NULL""", (livro_id, prazo)):
            liberar(db, reserva, "expirada")
        distribuir(db, livro_id, datetime.fromisoformat(prazo))
    hoje = instante.date()
    for emprestimo in linhas(db, """SELECT * FROM emprestimos WHERE data_devolucao IS NULL
                                   AND data_prevista < ?""", (hoje.isoformat(),)):
        atualizar_atraso(db, emprestimo, hoje)


@contextmanager
def transacao():
    db = sqlite3.connect(os.getenv("BIBLIOTECA_DB", "biblioteca.db"), timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        instante = agora()
        sincronizar(db, instante)
        db.execute("SAVEPOINT operacao")
        try:
            yield db, instante
        except (HTTPException, sqlite3.IntegrityError) as exc:
            db.execute("ROLLBACK TO operacao")
            db.commit()
            if isinstance(exc, sqlite3.IntegrityError):
                erro(409, "Registro duplicado ou vinculado a outros registros")
            raise
        db.commit()
    finally:
        db.close()


def usuario_publico(usuario, hoje):
    fim = usuario["suspenso_ate"]
    if fim and hoje.isoformat() < fim:
        usuario["situacao"] = "suspenso"
    else:
        usuario["suspenso_ate"] = None
    return usuario


def tem_acervo(db, livro_id):
    return db.execute(
        """SELECT 1 FROM exemplares WHERE livro_id = ?
           AND estado IN ('disponivel', 'emprestado', 'reservado') LIMIT 1""", (livro_id,)
    ).fetchone()


def cancelar_reservas_ativas(db, livro_id):
    for reserva in linhas(db, """SELECT * FROM reservas WHERE livro_id = ? AND atendida_em IS NULL
                                AND estado IN ('aguardando', 'disponivel')""", (livro_id,)):
        liberar(db, reserva, "cancelada")


def tratar_baixa(db, exemplar):
    livro_id = exemplar["livro_id"]
    disponivel = db.execute(
        "SELECT 1 FROM exemplares WHERE livro_id = ? AND estado = 'disponivel' LIMIT 1", (livro_id,)
    ).fetchone()
    if not tem_acervo(db, livro_id) or (exemplar["estado"] == "disponivel" and not disponivel):
        cancelar_reservas_ativas(db, livro_id)


def validar_exemplar(db, entrada, anterior=None):
    obter(db, "livros", entrada.livro_id)
    if anterior and anterior["livro_id"] != entrada.livro_id:
        erro(409, "O livro de um exemplar cadastrado é fixo")
    estado_anterior = anterior["estado"] if anterior else None
    if entrada.estado == estado_anterior:
        return
    if entrada.estado in ("emprestado", "reservado") or estado_anterior == "emprestado":
        erro(409, "Estado controlado pelo fluxo de empréstimos e reservas")
    if estado_anterior == "reservado":
        db.execute(
            """UPDATE reservas SET estado = 'aguardando', exemplar_id = NULL, disponivel_ate = NULL
               WHERE exemplar_id = ? AND estado = 'disponivel' AND atendida_em IS NULL""",
            (anterior["id"],),
        )


def cadastrar_crud(tabela, modelo):
    def publicar(row, instante):
        return usuario_publico(row, instante.date()) if tabela == "usuarios" else row

    def criar(entrada: modelo):
        with transacao() as (db, instante):
            if tabela == "exemplares":
                validar_exemplar(db, entrada)
            row = gravar(db, tabela, entrada.model_dump())
            if tabela == "exemplares":
                distribuir(db, entrada.livro_id, instante)
                row = obter(db, tabela, row["id"])
            return publicar(row, instante)

    def listar():
        with transacao() as (db, instante):
            return [publicar(row, instante) for row in linhas(db, f"SELECT * FROM {tabela} ORDER BY id")]

    def consultar(id: int):
        with transacao() as (db, instante):
            return publicar(obter(db, tabela, id), instante)

    def atualizar(id: int, entrada: modelo):
        with transacao() as (db, instante):
            anterior = obter(db, tabela, id)
            if tabela == "exemplares":
                validar_exemplar(db, entrada, anterior)
            row = gravar(db, tabela, entrada.model_dump(), id)
            if tabela == "exemplares":
                if entrada.estado == "baixado" and anterior["estado"] != "baixado":
                    tratar_baixa(db, anterior)
                distribuir(db, entrada.livro_id, instante)
                row = obter(db, tabela, id)
            return publicar(row, instante)

    def excluir(id: int):
        with transacao() as (db, _):
            anterior = obter(db, tabela, id)
            db.execute(f"DELETE FROM {tabela} WHERE id = ?", (id,))
            if tabela == "exemplares" and not tem_acervo(db, anterior["livro_id"]):
                cancelar_reservas_ativas(db, anterior["livro_id"])

    for sufixo, metodo, codigo, handler in (
        ("", "POST", 201, criar), ("", "GET", 200, listar),
        ("/{id}", "GET", 200, consultar), ("/{id}", "PUT", 200, atualizar),
        ("/{id}", "DELETE", 204, excluir),
    ):
        app.add_api_route(f"/{tabela}{sufixo}", handler, methods=[metodo],
                          status_code=codigo, name=f"{handler.__name__}_{tabela}")


cadastrar_crud("usuarios", Usuario)
cadastrar_crud("livros", Livro)
cadastrar_crud("exemplares", Exemplar)


def publicar_emprestimo(row):
    return {campo: valor for campo, valor in row.items() if campo != "categoria"}


@app.post("/emprestimos", status_code=201)
def criar_emprestimo(entrada: NovoEmprestimo):
    with transacao() as (db, instante):
        hoje = instante.date()
        usuario = usuario_publico(obter(db, "usuarios", entrada.usuario_id), hoje)
        exemplar = obter(db, "exemplares", entrada.exemplar_id)
        if usuario["situacao"] != "ativo":
            erro(403, "Usuário suspenso")
        if db.execute(
            """SELECT 1 FROM multas m JOIN emprestimos e ON e.id = m.emprestimo_id
               WHERE e.usuario_id = ? AND m.estado = 'aberta'""", (entrada.usuario_id,)
        ).fetchone():
            erro(409, "Usuário possui multa aberta")
        limite, prazo, *_ = REGRAS[usuario["categoria"]]
        em_curso = db.execute(
            "SELECT COUNT(*) FROM emprestimos WHERE usuario_id = ? AND data_devolucao IS NULL",
            (entrada.usuario_id,),
        ).fetchone()[0]
        if em_curso >= limite:
            erro(409, "Limite de exemplares atingido")
        reserva = db.execute(
            """SELECT id FROM reservas WHERE exemplar_id = ? AND usuario_id = ?
               AND estado = 'disponivel' AND atendida_em IS NULL""", (entrada.exemplar_id, entrada.usuario_id)
        ).fetchone()
        if exemplar["estado"] != "disponivel" and not reserva:
            erro(409, "Exemplar indisponível para este usuário")
        if reserva:
            gravar(db, "reservas", {"atendida_em": instante.isoformat(), "exemplar_id": None}, reserva["id"])
        gravar(db, "exemplares", {"estado": "emprestado"}, entrada.exemplar_id)
        return publicar_emprestimo(gravar(db, "emprestimos", {
            **entrada.model_dump(), "data_retirada": hoje.isoformat(),
            "data_prevista": (hoje + timedelta(days=prazo)).isoformat(),
            "categoria": usuario["categoria"], "estado": "ativo",
        }))


@app.post("/emprestimos/{id}/renovar")
def renovar_emprestimo(id: int):
    with transacao() as (db, _):
        emprestimo = obter(db, "emprestimos", id)
        if emprestimo["estado"] != "ativo":
            erro(409, "A renovação exige um empréstimo ativo e em dia")
        exemplar = obter(db, "exemplares", emprestimo["exemplar_id"])
        if fila_reservas(db, exemplar["livro_id"]):
            erro(409, "O livro possui fila de reserva")
        _, prazo, limite, *_ = REGRAS[emprestimo["categoria"]]
        if emprestimo["numero_renovacoes"] >= limite:
            erro(409, "Limite de renovações atingido")
        prevista = date.fromisoformat(emprestimo["data_prevista"]) + timedelta(days=prazo)
        return publicar_emprestimo(gravar(db, "emprestimos", {
            "data_prevista": prevista.isoformat(),
            "numero_renovacoes": emprestimo["numero_renovacoes"] + 1,
        }, id))


@app.post("/emprestimos/{id}/devolver")
def devolver_emprestimo(id: int):
    with transacao() as (db, instante):
        emprestimo = obter(db, "emprestimos", id)
        if emprestimo["data_devolucao"]:
            erro(409, "Empréstimo já devolvido")
        hoje = instante.date()
        atualizar_atraso(db, emprestimo, hoje, devolvendo=True)
        exemplar = obter(db, "exemplares", emprestimo["exemplar_id"])
        baixado = dias_atraso(emprestimo, hoje) > 60
        gravar(db, "exemplares", {"estado": "baixado" if baixado else "disponivel"}, exemplar["id"])
        if baixado:
            tratar_baixa(db, exemplar)
        distribuir(db, exemplar["livro_id"], instante)
        return publicar_emprestimo(gravar(db, "emprestimos", {
            "estado": "devolvido", "data_devolucao": hoje.isoformat(),
        }, id))


@app.get("/usuarios/{id}/emprestimos")
def listar_emprestimos(id: int):
    with transacao() as (db, _):
        obter(db, "usuarios", id)
        return [publicar_emprestimo(row) for row in linhas(
            db, "SELECT * FROM emprestimos WHERE usuario_id = ? ORDER BY id", (id,)
        )]


def fila_reservas(db, livro_id):
    fila = linhas(db, """SELECT id, livro_id, usuario_id, data, estado, disponivel_ate, exemplar_id
                        FROM reservas WHERE livro_id = ? AND atendida_em IS NULL
                        AND estado IN ('aguardando', 'disponivel') ORDER BY id""", (livro_id,))
    for posicao, reserva in enumerate(fila, 1):
        reserva["posicao_fila"] = posicao
    return fila


@app.post("/reservas", status_code=201)
def criar_reserva(entrada: NovaReserva):
    with transacao() as (db, instante):
        obter(db, "usuarios", entrada.usuario_id)
        obter(db, "livros", entrada.livro_id)
        if not tem_acervo(db, entrada.livro_id):
            erro(409, "Livro sem exemplares aptos para reserva")
        reserva = gravar(db, "reservas", {
            **entrada.model_dump(), "data": instante.isoformat(), "estado": "aguardando",
        })
        distribuir(db, entrada.livro_id, instante)
        return next(item for item in fila_reservas(db, entrada.livro_id) if item["id"] == reserva["id"])


@app.post("/reservas/{id}/cancelar")
def cancelar_reserva(id: int):
    with transacao() as (db, instante):
        reserva = obter(db, "reservas", id)
        if reserva["atendida_em"] or reserva["estado"] not in ("aguardando", "disponivel"):
            erro(409, "Reserva fora da fila")
        liberar(db, reserva, "cancelada")
        distribuir(db, reserva["livro_id"], instante)
        return {**obter(db, "reservas", id), "posicao_fila": None}


@app.get("/livros/{id}/reservas")
def listar_fila(id: int):
    with transacao() as (db, _):
        obter(db, "livros", id)
        return fila_reservas(db, id)


def publicar_multa(multa):
    centavos = multa.pop("centavos")
    return {**multa, "valor": centavos / 100}


@app.get("/usuarios/{id}/multas")
def listar_multas(id: int):
    with transacao() as (db, _):
        obter(db, "usuarios", id)
        return [publicar_multa(row) for row in linhas(
            db, """SELECT m.* FROM multas m JOIN emprestimos e ON e.id = m.emprestimo_id
                   WHERE e.usuario_id = ? ORDER BY m.id""", (id,)
        )]


@app.post("/multas/{id}/pagamento")
def pagar_multa(id: int):
    with transacao() as (db, _):
        multa = obter(db, "multas", id)
        if multa["estado"] != "aberta":
            erro(409, "A multa precisa estar aberta")
        if obter(db, "emprestimos", multa["emprestimo_id"])["data_devolucao"] is None:
            erro(409, "Registre a devolução para liquidar o valor definitivo")
        return publicar_multa(gravar(db, "multas", {"estado": "paga"}, id))


@app.get("/relatorios/livros-mais-emprestados")
def livros_mais_emprestados(inicio: date, fim: date, limite: int = Query(default=10, ge=1, le=100)):
    if inicio > fim:
        erro(422, "A data inicial deve ser anterior ou igual à final")
    with transacao() as (db, _):
        return linhas(db, """SELECT l.id AS livro_id, l.titulo, COUNT(*) AS total_emprestimos
                            FROM emprestimos e JOIN exemplares x ON x.id = e.exemplar_id
                            JOIN livros l ON l.id = x.livro_id WHERE e.data_retirada BETWEEN ? AND ?
                            GROUP BY l.id ORDER BY total_emprestimos DESC, l.id LIMIT ?""",
                      (inicio.isoformat(), fim.isoformat(), limite))


@app.get("/relatorios/usuarios-com-mais-atrasos")
def usuarios_com_mais_atrasos(limite: int = Query(default=10, ge=1, le=100)):
    with transacao() as (db, instante):
        return linhas(db, """SELECT u.id AS usuario_id, u.nome, COUNT(*) AS total_atrasos
                            FROM usuarios u JOIN emprestimos e ON e.usuario_id = u.id
                            WHERE COALESCE(e.data_devolucao, ?) > e.data_prevista
                            GROUP BY u.id ORDER BY total_atrasos DESC, u.id LIMIT ?""",
                      (instante.date().isoformat(), limite))


@app.get("/relatorios/ocupacao-por-area")
def ocupacao_por_area():
    with transacao() as (db, _):
        return linhas(db, """SELECT l.area_conhecimento, COUNT(x.id) AS total_operacional,
                            SUM(CASE WHEN x.estado = 'emprestado' THEN 1 ELSE 0 END) AS emprestados,
                            COALESCE(ROUND(100.0 * SUM(CASE WHEN x.estado = 'emprestado'
                                     THEN 1 ELSE 0 END) / NULLIF(COUNT(x.id), 0), 2), 0.0)
                            AS taxa_ocupacao_percentual
                            FROM livros l LEFT JOIN exemplares x ON x.livro_id = l.id
                            AND x.estado IN ('disponivel', 'emprestado', 'reservado')
                            GROUP BY l.area_conhecimento ORDER BY l.area_conhecimento""")
