from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal
import os
import re
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Path as ParamPath, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ROOT = Path(__file__).resolve().parent
REGRAS = {
    "aluno": (3, 7, 2, 100, 3000),
    "professor": (8, 30, 4, 50, 5000),
    "visitante": (1, 3, 0, 200, 2000),
}
Categoria = Literal["aluno", "professor", "visitante"]
Situacao = Literal["ativo", "suspenso"]
EstadoExemplar = Literal["disponivel", "emprestado", "reservado", "em_reparo", "baixado"]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Id = Annotated[int, ParamPath(gt=0)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Usuario(Entrada):
    nome: Texto
    email: Texto
    matricula: Texto
    categoria: Categoria
    situacao: Situacao = "ativo"

    @field_validator("email")
    @classmethod
    def validar_email(cls, valor: str) -> str:
        if not re.fullmatch(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+", valor):
            raise ValueError("E-mail invalido")
        return valor


class Livro(Entrada):
    titulo: Texto
    autor: Texto
    isbn: Texto
    ano: int = Field(ge=1, le=9999)
    area_conhecimento: Texto

    @field_validator("isbn")
    @classmethod
    def normalizar_isbn(cls, valor: str) -> str:
        valor = valor.replace("-", "").replace(" ", "").upper()
        if not re.fullmatch(r"(?:[0-9]{9}[0-9X]|[0-9]{13})", valor):
            raise ValueError("Informe um ISBN de 10 ou 13 caracteres")
        return valor


class Exemplar(Entrada):
    livro_id: int = Field(gt=0)
    codigo_tombo: Texto
    estado: EstadoExemplar = "disponivel"


class NovoEmprestimo(Entrada):
    exemplar_id: int = Field(gt=0)
    usuario_id: int = Field(gt=0)


class NovaReserva(Entrada):
    livro_id: int = Field(gt=0)
    usuario_id: int = Field(gt=0)


def agora():
    return datetime.now(timezone.utc)


def conectar():
    db = sqlite3.connect(os.environ.get("BIBLIOTECA_DB", ROOT / "biblioteca.db"), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


@asynccontextmanager
async def lifespan(app):
    db = conectar()
    try:
        db.executescript((ROOT / "schema.sql").read_text(encoding="ascii"))
    finally:
        db.close()
    yield


app = FastAPI(title="Biblioteca Universitaria", lifespan=lifespan)


def executar(db, sql, *params):
    return db.execute(sql, params)


def todos(db, sql, *params):
    return [dict(row) for row in executar(db, sql, *params)]


def obter(db, tabela, id):
    row = executar(db, f"SELECT * FROM {tabela} WHERE id = ?", id).fetchone()
    if row is None:
        raise HTTPException(404, "Registro nao encontrado")
    return dict(row)


def conflito(mensagem):
    raise HTTPException(409, mensagem)


def inserir(db, tabela, valores):
    campos = ", ".join(valores)
    marcadores = ", ".join("?" for _ in valores)
    cursor = executar(db, f"INSERT INTO {tabela} ({campos}) VALUES ({marcadores})", *valores.values())
    return obter(db, tabela, cursor.lastrowid)


def editar(db, tabela, id, **valores):
    campos = ", ".join(f"{campo} = ?" for campo in valores)
    executar(db, f"UPDATE {tabela} SET {campos} WHERE id = ?", *valores.values(), id)
    return obter(db, tabela, id)


def atraso(emprestimo, instante):
    return max(0, (instante.date() - date.fromisoformat(emprestimo["data_prevista"])).days)


def atualizar_multa(db, emprestimo, dias):
    categoria = emprestimo["categoria"]
    _, _, _, diaria, teto = REGRAS[categoria]
    if dias == 0:
        return
    valor = min(dias * diaria, teto)
    if dias > 60 and emprestimo["data_devolucao"]:
        valor = teto
    estado = "perdoada" if categoria == "professor" and dias <= 2 else "aberta"
    executar(db, """
        INSERT INTO multas (emprestimo_id, valor_centavos, estado) VALUES (?, ?, ?)
        ON CONFLICT(emprestimo_id) DO UPDATE SET
            valor_centavos = excluded.valor_centavos,
            estado = CASE WHEN multas.valor_pago_centavos >= excluded.valor_centavos
                THEN 'paga' ELSE excluded.estado END
    """, emprestimo["id"], valor, estado)


def distribuir(db, livro_id, instante):
    fila = todos(db, """
        SELECT id, data FROM reservas WHERE livro_id = ? AND estado = 'aguardando' ORDER BY id
    """, livro_id)
    exemplares = todos(db, """
        SELECT id FROM exemplares WHERE livro_id = ? AND estado = 'disponivel' ORDER BY id
    """, livro_id)
    for reserva, exemplar in zip(fila, exemplares):
        editar(db, "reservas", reserva["id"], estado="disponivel", exemplar_id=exemplar["id"],
               disponivel_ate=(max(instante, datetime.fromisoformat(reserva["data"])) + timedelta(hours=48)).isoformat())
        editar(db, "exemplares", exemplar["id"], estado="reservado")


def sincronizar(db, instante):
    executar(db, "UPDATE usuarios SET suspenso_ate = NULL WHERE suspenso_ate <= ?", instante.isoformat())
    pendentes = todos(db, """
        SELECT * FROM emprestimos WHERE data_devolucao IS NULL AND data_prevista < ?
    """, instante.date().isoformat())
    for emprestimo in pendentes:
        if emprestimo["estado"] != "atrasado":
            editar(db, "emprestimos", emprestimo["id"], estado="atrasado")
        atualizar_multa(db, emprestimo, atraso(emprestimo, instante))
    # Process handoffs in chronological order after periods without requests.
    while oferta := executar(db, """
        SELECT * FROM reservas WHERE estado = 'disponivel' AND atendida_em IS NULL
        AND disponivel_ate <= ? ORDER BY disponivel_ate, id LIMIT 1
    """, instante.isoformat()).fetchone():
        prazo = datetime.fromisoformat(oferta["disponivel_ate"])
        editar(db, "reservas", oferta["id"], estado="expirada")
        editar(db, "exemplares", oferta["exemplar_id"], estado="disponivel")
        distribuir(db, oferta["livro_id"], prazo)

def transacao():
    db = conectar()
    try:
        executar(db, "BEGIN IMMEDIATE")
        instante = agora()
        sincronizar(db, instante)
        executar(db, "SAVEPOINT operacao")
        try:
            yield db, instante
        except (HTTPException, sqlite3.IntegrityError) as erro:
            executar(db, "ROLLBACK TO operacao")
            db.commit()
            if isinstance(erro, sqlite3.IntegrityError):
                raise HTTPException(409, "Registro duplicado ou vinculado a outros registros") from erro
            raise
        else:
            db.commit()
    finally:
        db.close()


Transacao = Annotated[tuple, Depends(transacao, scope="function")]


def usuario_publico(db, usuario, instante):
    limite = (instante.date() - timedelta(days=15)).isoformat()
    atraso_grave = executar(db, """
        SELECT 1 FROM emprestimos WHERE usuario_id = ? AND data_devolucao IS NULL
        AND data_prevista < ? LIMIT 1
    """, usuario["id"], limite).fetchone()
    if usuario["suspenso_ate"] or atraso_grave:
        usuario["situacao"] = "suspenso"
    return usuario


def excluir(db, tabela, id):
    obter(db, tabela, id)
    executar(db, f"DELETE FROM {tabela} WHERE id = ?", id)
    return Response(status_code=204)


@app.post("/usuarios", status_code=201)
def criar_usuario(dados: Usuario, tx: Transacao):
    return inserir(tx[0], "usuarios", dados.model_dump())


@app.get("/usuarios")
def listar_usuarios(tx: Transacao):
    db, instante = tx
    return [usuario_publico(db, u, instante) for u in todos(db, "SELECT * FROM usuarios ORDER BY id")]


@app.get("/usuarios/{id}")
def consultar_usuario(id: Id, tx: Transacao):
    db, instante = tx
    return usuario_publico(db, obter(db, "usuarios", id), instante)


@app.put("/usuarios/{id}")
def atualizar_usuario(id: Id, dados: Usuario, tx: Transacao):
    db, instante = tx
    obter(db, "usuarios", id)
    return usuario_publico(db, editar(db, "usuarios", id, **dados.model_dump()), instante)


@app.delete("/usuarios/{id}", status_code=204)
def excluir_usuario(id: Id, tx: Transacao):
    return excluir(tx[0], "usuarios", id)


@app.post("/livros", status_code=201)
def criar_livro(dados: Livro, tx: Transacao):
    return inserir(tx[0], "livros", dados.model_dump())


@app.get("/livros")
def listar_livros(tx: Transacao):
    return todos(tx[0], "SELECT * FROM livros ORDER BY id")


@app.get("/livros/{id}")
def consultar_livro(id: Id, tx: Transacao):
    return obter(tx[0], "livros", id)


@app.put("/livros/{id}")
def atualizar_livro(id: Id, dados: Livro, tx: Transacao):
    obter(tx[0], "livros", id)
    return editar(tx[0], "livros", id, **dados.model_dump())


@app.delete("/livros/{id}", status_code=204)
def excluir_livro(id: Id, tx: Transacao):
    return excluir(tx[0], "livros", id)


def estado_administrativo(estado):
    if estado in ("reservado", "emprestado"):
        conflito("Estado definido pelo fluxo de reservas ou emprestimos")


def cancelar_fila(db, livro_id):
    executar(db, """
        UPDATE exemplares SET estado = 'disponivel' WHERE livro_id = ? AND estado = 'reservado'
    """, livro_id)
    executar(db, """
        UPDATE reservas SET estado = 'cancelada'
        WHERE livro_id = ? AND atendida_em IS NULL AND estado IN ('aguardando', 'disponivel')
    """, livro_id)


def ajustar_acervo(db, livro_id, instante, baixou_disponivel=False):
    estados = ("disponivel", "reservado") if baixou_disponivel else ("disponivel", "reservado", "emprestado")
    marcadores = ", ".join("?" for _ in estados)
    if executar(db, f"SELECT 1 FROM exemplares WHERE livro_id = ? AND estado IN ({marcadores})",
                livro_id, *estados).fetchone():
        distribuir(db, livro_id, instante)
    else:
        cancelar_fila(db, livro_id)


@app.post("/exemplares", status_code=201)
def criar_exemplar(dados: Exemplar, tx: Transacao):
    db, instante = tx
    obter(db, "livros", dados.livro_id)
    estado_administrativo(dados.estado)
    exemplar = inserir(db, "exemplares", dados.model_dump())
    distribuir(db, dados.livro_id, instante)
    return obter(db, "exemplares", exemplar["id"])


@app.get("/exemplares")
def listar_exemplares(tx: Transacao):
    return todos(tx[0], "SELECT * FROM exemplares ORDER BY id")


@app.get("/exemplares/{id}")
def consultar_exemplar(id: Id, tx: Transacao):
    return obter(tx[0], "exemplares", id)


@app.put("/exemplares/{id}")
def atualizar_exemplar(id: Id, dados: Exemplar, tx: Transacao):
    db, instante = tx
    exemplar = obter(db, "exemplares", id)
    obter(db, "livros", dados.livro_id)
    if dados.livro_id != exemplar["livro_id"]:
        if executar(db, "SELECT 1 FROM emprestimos WHERE exemplar_id = ?", id).fetchone() or executar(
            db, "SELECT 1 FROM reservas WHERE exemplar_id = ?", id
        ).fetchone():
            conflito("Exemplar com historico vinculado ao livro")
    if exemplar["estado"] == "emprestado" and dados.estado != "emprestado":
        conflito("Devolva o exemplar antes de alterar seu estado")
    if exemplar["estado"] != dados.estado:
        estado_administrativo(dados.estado)
        if exemplar["estado"] == "reservado":
            executar(db, """
                UPDATE reservas SET estado = 'aguardando', exemplar_id = NULL, disponivel_ate = NULL
                WHERE exemplar_id = ? AND estado = 'disponivel' AND atendida_em IS NULL
            """, id)
    editar(db, "exemplares", id, **dados.model_dump())
    ajustou_baixa = dados.estado == "baixado" and exemplar["estado"] in ("disponivel", "reservado")
    ajustar_acervo(db, exemplar["livro_id"], instante, ajustou_baixa)
    if dados.livro_id != exemplar["livro_id"]:
        distribuir(db, dados.livro_id, instante)
    return obter(db, "exemplares", id)


@app.delete("/exemplares/{id}", status_code=204)
def excluir_exemplar(id: Id, tx: Transacao):
    db, instante = tx
    exemplar = obter(db, "exemplares", id)
    resposta = excluir(db, "exemplares", id)
    ajustar_acervo(db, exemplar["livro_id"], instante)
    return resposta



def emprestimo_publico(emprestimo):
    return {campo: valor for campo, valor in emprestimo.items() if campo != "categoria"}


@app.post("/emprestimos", status_code=201)
def criar_emprestimo(dados: NovoEmprestimo, tx: Transacao):
    db, instante = tx
    usuario = usuario_publico(db, obter(db, "usuarios", dados.usuario_id), instante)
    exemplar = obter(db, "exemplares", dados.exemplar_id)
    if usuario["situacao"] != "ativo":
        conflito("Usuario suspenso")
    if executar(db, """
        SELECT 1 FROM multas m JOIN emprestimos e ON e.id = m.emprestimo_id
        WHERE e.usuario_id = ? AND m.estado = 'aberta'
    """, dados.usuario_id).fetchone():
        conflito("Usuario possui multa aberta")
    limite, prazo, *_ = REGRAS[usuario["categoria"]]
    quantidade = executar(db, """
        SELECT COUNT(*) FROM emprestimos WHERE usuario_id = ? AND data_devolucao IS NULL
    """, dados.usuario_id).fetchone()[0]
    if quantidade >= limite:
        conflito("Limite de exemplares atingido")
    if exemplar["estado"] == "reservado":
        reserva = executar(db, """
            SELECT id FROM reservas WHERE exemplar_id = ? AND usuario_id = ?
            AND estado = 'disponivel' AND atendida_em IS NULL
        """, dados.exemplar_id, dados.usuario_id).fetchone()
        if not reserva:
            conflito("Exemplar reservado para outro usuario")
        editar(db, "reservas", reserva["id"], atendida_em=instante.isoformat())
    elif exemplar["estado"] != "disponivel":
        conflito("Exemplar indisponivel")
    emprestimo = inserir(db, "emprestimos", {
        **dados.model_dump(),
        "categoria": usuario["categoria"],
        "data_retirada": instante.isoformat(),
        "data_prevista": (instante.date() + timedelta(days=prazo)).isoformat(),
        "estado": "ativo",
    })
    editar(db, "exemplares", dados.exemplar_id, estado="emprestado")
    return emprestimo_publico(emprestimo)


@app.get("/usuarios/{id}/emprestimos")
def listar_emprestimos(id: Id, tx: Transacao):
    db, _ = tx
    obter(db, "usuarios", id)
    return [emprestimo_publico(e) for e in todos(db, """
        SELECT * FROM emprestimos WHERE usuario_id = ? ORDER BY id
    """, id)]


@app.post("/emprestimos/{id}/renovar")
def renovar_emprestimo(id: Id, tx: Transacao):
    db, _ = tx
    emprestimo = obter(db, "emprestimos", id)
    if emprestimo["estado"] != "ativo":
        conflito("O emprestimo precisa estar ativo e dentro do prazo")
    _, prazo, limite, *_ = REGRAS[emprestimo["categoria"]]
    if emprestimo["numero_renovacoes"] >= limite:
        conflito("Limite de renovacoes atingido")
    exemplar = obter(db, "exemplares", emprestimo["exemplar_id"])
    if executar(db, """
        SELECT 1 FROM reservas WHERE livro_id = ? AND atendida_em IS NULL
        AND estado IN ('aguardando', 'disponivel')
    """, exemplar["livro_id"]).fetchone():
        conflito("Livro possui fila de reserva")
    prevista = date.fromisoformat(emprestimo["data_prevista"]) + timedelta(days=prazo)
    return emprestimo_publico(editar(db, "emprestimos", id, data_prevista=prevista.isoformat(),
                                   numero_renovacoes=emprestimo["numero_renovacoes"] + 1))


@app.post("/emprestimos/{id}/devolver")
def devolver_emprestimo(id: Id, tx: Transacao):
    db, instante = tx
    emprestimo = obter(db, "emprestimos", id)
    if emprestimo["data_devolucao"]:
        conflito("Emprestimo ja devolvido")
    dias = atraso(emprestimo, instante)
    emprestimo = editar(db, "emprestimos", id, estado="devolvido", data_devolucao=instante.isoformat())
    atualizar_multa(db, emprestimo, dias)
    if dias > 15:
        usuario = obter(db, "usuarios", emprestimo["usuario_id"])
        inicio = date.fromisoformat(emprestimo["data_prevista"]) + timedelta(days=16)
        fim = datetime.combine(inicio + timedelta(days=2 * dias), datetime.min.time(),
                               tzinfo=timezone.utc).isoformat()
        editar(db, "usuarios", usuario["id"], suspenso_ate=max(fim, usuario["suspenso_ate"] or fim))
    estado = "baixado" if dias > 60 else "disponivel"
    exemplar = editar(db, "exemplares", emprestimo["exemplar_id"], estado=estado)
    ajustar_acervo(db, exemplar["livro_id"], instante)
    return emprestimo_publico(emprestimo)


def fila_livro(db, livro_id):
    fila = todos(db, """
        SELECT * FROM reservas WHERE livro_id = ? AND atendida_em IS NULL
        AND estado IN ('aguardando', 'disponivel') ORDER BY id
    """, livro_id)
    for posicao, reserva in enumerate(fila, start=1):
        reserva["posicao_fila"] = posicao
    return fila


@app.post("/reservas", status_code=201)
def criar_reserva(dados: NovaReserva, tx: Transacao):
    db, instante = tx
    obter(db, "usuarios", dados.usuario_id)
    obter(db, "livros", dados.livro_id)
    if not executar(db, """
        SELECT 1 FROM exemplares WHERE livro_id = ? AND estado IN ('disponivel', 'reservado', 'emprestado')
    """, dados.livro_id).fetchone():
        conflito("Livro sem exemplar elegivel para reserva")
    reserva = inserir(db, "reservas", {
        **dados.model_dump(), "data": instante.isoformat(), "estado": "aguardando",
    })
    distribuir(db, dados.livro_id, instante)
    return next(item for item in fila_livro(db, dados.livro_id) if item["id"] == reserva["id"])


@app.get("/livros/{id}/reservas")
def listar_fila(id: Id, tx: Transacao):
    db, _ = tx
    obter(db, "livros", id)
    return fila_livro(db, id)


@app.post("/reservas/{id}/cancelar")
def cancelar_reserva(id: Id, tx: Transacao):
    db, instante = tx
    reserva = obter(db, "reservas", id)
    if reserva["atendida_em"] or reserva["estado"] not in ("aguardando", "disponivel"):
        conflito("Reserva ja encerrada")
    reserva = editar(db, "reservas", id, estado="cancelada")
    if reserva["exemplar_id"]:
        editar(db, "exemplares", reserva["exemplar_id"], estado="disponivel")
        distribuir(db, reserva["livro_id"], instante)
    return {**reserva, "posicao_fila": None}


def multa_publica(multa):
    saldo = multa["valor_centavos"] - multa["valor_pago_centavos"] if multa["estado"] == "aberta" else 0
    return {
        **multa, "valor": multa["valor_centavos"] / 100,
        "saldo_centavos": saldo, "saldo": saldo / 100,
    }


@app.get("/usuarios/{id}/multas")
def listar_multas(id: Id, tx: Transacao):
    db, _ = tx
    obter(db, "usuarios", id)
    return [multa_publica(m) for m in todos(db, """
        SELECT m.* FROM multas m JOIN emprestimos e ON e.id = m.emprestimo_id
        WHERE e.usuario_id = ? ORDER BY m.id
    """, id)]


@app.post("/multas/{id}/pagar")
def pagar_multa(id: Id, tx: Transacao):
    db, _ = tx
    multa = obter(db, "multas", id)
    if multa["estado"] != "aberta":
        conflito("Multa sem saldo em aberto")
    return multa_publica(editar(db, "multas", id, estado="paga", valor_pago_centavos=multa["valor_centavos"]))


@app.get("/relatorios/livros-mais-emprestados")
def livros_mais_emprestados(inicio: date, fim: date, tx: Transacao):
    if inicio > fim:
        raise HTTPException(422, "A data inicial precisa anteceder ou coincidir com a data final")
    return todos(tx[0], """
        SELECT l.id AS livro_id, l.titulo, COUNT(*) AS total_emprestimos
        FROM emprestimos e JOIN exemplares x ON x.id = e.exemplar_id JOIN livros l ON l.id = x.livro_id
        WHERE substr(e.data_retirada, 1, 10) BETWEEN ? AND ?
        GROUP BY l.id ORDER BY total_emprestimos DESC, l.id
    """, inicio.isoformat(), fim.isoformat())


@app.get("/relatorios/usuarios-com-mais-atrasos")
def usuarios_com_mais_atrasos(tx: Transacao):
    return todos(tx[0], """
        SELECT u.id AS usuario_id, u.nome, COUNT(*) AS total_atrasos
        FROM emprestimos e JOIN usuarios u ON u.id = e.usuario_id
        WHERE e.estado = 'atrasado' OR substr(e.data_devolucao, 1, 10) > e.data_prevista
        GROUP BY u.id ORDER BY total_atrasos DESC, u.id
    """)


@app.get("/relatorios/ocupacao-por-area")
def ocupacao_por_area(tx: Transacao):
    return todos(tx[0], """
        SELECT l.area_conhecimento, COUNT(x.id) AS total_exemplares,
               COALESCE(SUM(x.estado = 'emprestado'), 0) AS exemplares_emprestados,
               COALESCE(1.0 * SUM(x.estado = 'emprestado') / COUNT(x.id), 0.0) AS taxa_ocupacao
        FROM livros l LEFT JOIN exemplares x ON x.livro_id = l.id AND x.estado != 'baixado'
        GROUP BY l.area_conhecimento ORDER BY l.area_conhecimento
    """)

