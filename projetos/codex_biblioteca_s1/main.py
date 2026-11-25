import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
import logging
import sqlite3
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

import biblioteca as b


def manutencao():
    with b.transacao() as db:
        b.sincronizar(db, b.agora_utc())


async def atualizar_periodicamente():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(manutencao)
        except sqlite3.Error:
            logging.getLogger(__name__).exception("Falha ao atualizar a circulação")


@asynccontextmanager
async def lifespan(_app):
    await asyncio.to_thread(b.inicializar)
    await asyncio.to_thread(manutencao)
    tarefa = asyncio.create_task(atualizar_periodicamente())
    try:
        yield
    finally:
        tarefa.cancel()
        await asyncio.gather(tarefa, return_exceptions=True)


app = FastAPI(title="Biblioteca Universitária", lifespan=lifespan)


@dataclass
class Contexto:
    db: sqlite3.Connection
    agora: datetime
    hoje: date


def contexto():
    try:
        with b.transacao() as db:
            agora = b.agora_utc()
            yield Contexto(db, agora, b.sincronizar(db, agora))
    except sqlite3.IntegrityError as erro:
        if erro.sqlite_errorname == "SQLITE_CONSTRAINT_FOREIGNKEY":
            b.conflito("O registro possui vínculos no acervo ou no histórico de circulação.")
        if erro.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE":
            b.conflito("Já existe um registro com os mesmos dados únicos.")
        raise
    except sqlite3.OperationalError as erro:
        if erro.sqlite_errorcode in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise HTTPException(503, "Banco temporariamente ocupado.") from erro
        raise


Ctx = Annotated[Contexto, Depends(contexto, scope="function")]
Id = Annotated[int, Field(strict=True, gt=0)]
IdRota = Annotated[int, Path(gt=0)]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Email = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
]


class Categoria(StrEnum):
    ALUNO = "aluno"
    PROFESSOR = "professor"
    VISITANTE = "visitante"


class Situacao(StrEnum):
    ATIVO = "ativo"
    SUSPENSO = "suspenso"


class EstadoAdministrativo(StrEnum):
    DISPONIVEL = "disponivel"
    EM_REPARO = "em_reparo"
    BAIXADO = "baixado"


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Usuario(Entrada):
    nome: Texto
    email: Email
    matricula: Texto
    categoria: Categoria
    situacao: Situacao = Situacao.ATIVO


class Livro(Entrada):
    titulo: Texto
    autor: Texto
    isbn: Texto
    ano: Annotated[int, Field(strict=True, ge=1, le=9999)]
    area_conhecimento: Texto

    @field_validator("isbn")
    @classmethod
    def validar_isbn(cls, valor):
        isbn = valor.replace("-", "").replace(" ", "").upper()
        if len(isbn) == 13 and isbn.isascii() and isbn.isdigit() and isbn.startswith(("978", "979")):
            if sum(int(digito) * (1 if i % 2 == 0 else 3) for i, digito in enumerate(isbn)) % 10 == 0:
                return isbn
        if len(isbn) == 10 and isbn[:9].isascii() and isbn[:9].isdigit() and isbn[-1] in "0123456789X":
            digitos = [int(digito) for digito in isbn[:9]] + [10 if isbn[-1] == "X" else int(isbn[-1])]
            if sum(digito * (10 - i) for i, digito in enumerate(digitos)) % 11 == 0:
                return isbn
        raise ValueError("Informe um ISBN-10 ou ISBN-13 válido.")


class Exemplar(Entrada):
    livro_id: Id
    codigo_tombo: Texto
    estado: EstadoAdministrativo | None = None


class NovoEmprestimo(Entrada):
    exemplar_id: Id
    usuario_id: Id


class NovaReserva(Entrada):
    livro_id: Id
    usuario_id: Id


def excluir(ctx, tabela, registro_id):
    b.obter(ctx.db, tabela, registro_id)
    ctx.db.execute(f"DELETE FROM {tabela} WHERE id = ?", (registro_id,))
    return Response(status_code=204)


@app.post("/usuarios", status_code=201)
def criar_usuario(dados: Usuario, ctx: Ctx):
    usuario = b.inserir(ctx.db, "usuarios", dados.model_dump(mode="json"))
    return b.usuario_publico(ctx.db, usuario, ctx.hoje)


@app.get("/usuarios")
def listar_usuarios(ctx: Ctx):
    return [
        b.usuario_publico(ctx.db, usuario, ctx.hoje)
        for usuario in b.listar(ctx.db, "SELECT * FROM usuarios ORDER BY id")
    ]


@app.get("/usuarios/{usuario_id}")
def consultar_usuario(usuario_id: IdRota, ctx: Ctx):
    return b.usuario_publico(ctx.db, b.obter(ctx.db, "usuarios", usuario_id), ctx.hoje)


@app.put("/usuarios/{usuario_id}")
def editar_usuario(usuario_id: IdRota, dados: Usuario, ctx: Ctx):
    usuario = b.atualizar(ctx.db, "usuarios", usuario_id, **dados.model_dump(mode="json"))
    return b.usuario_publico(ctx.db, usuario, ctx.hoje)


@app.delete("/usuarios/{usuario_id}", status_code=204)
def excluir_usuario(usuario_id: IdRota, ctx: Ctx):
    return excluir(ctx, "usuarios", usuario_id)


@app.post("/livros", status_code=201)
def criar_livro(dados: Livro, ctx: Ctx):
    return b.inserir(ctx.db, "livros", dados.model_dump())


@app.get("/livros")
def listar_livros(ctx: Ctx):
    return b.listar(ctx.db, "SELECT * FROM livros ORDER BY id")


@app.get("/livros/{livro_id}")
def consultar_livro(livro_id: IdRota, ctx: Ctx):
    return b.obter(ctx.db, "livros", livro_id)


@app.put("/livros/{livro_id}")
def editar_livro(livro_id: IdRota, dados: Livro, ctx: Ctx):
    return b.atualizar(ctx.db, "livros", livro_id, **dados.model_dump())


@app.delete("/livros/{livro_id}", status_code=204)
def excluir_livro(livro_id: IdRota, ctx: Ctx):
    return excluir(ctx, "livros", livro_id)


@app.post("/exemplares", status_code=201)
def criar_exemplar(dados: Exemplar, ctx: Ctx):
    b.obter(ctx.db, "livros", dados.livro_id)
    return b.inserir(ctx.db, "exemplares", {
        "livro_id": dados.livro_id,
        "codigo_tombo": dados.codigo_tombo,
        "estado": dados.estado or "disponivel",
    })


@app.get("/exemplares")
def listar_exemplares(ctx: Ctx):
    return b.listar(ctx.db, "SELECT * FROM exemplares ORDER BY id")


@app.get("/exemplares/{exemplar_id}")
def consultar_exemplar(exemplar_id: IdRota, ctx: Ctx):
    return b.obter(ctx.db, "exemplares", exemplar_id)


@app.put("/exemplares/{exemplar_id}")
def editar_exemplar(exemplar_id: IdRota, dados: Exemplar, ctx: Ctx):
    db = ctx.db
    exemplar = b.obter(db, "exemplares", exemplar_id)
    b.obter(db, "livros", dados.livro_id)
    anterior = exemplar["estado"]
    estado = dados.estado or anterior
    mudou_livro = dados.livro_id != exemplar["livro_id"]
    if mudou_livro and (
        anterior in {"emprestado", "reservado"} or db.execute(
            "SELECT 1 FROM emprestimos WHERE exemplar_id = ?", (exemplar_id,)
        ).fetchone()
    ):
        b.conflito("O exemplar possui histórico de circulação ou reserva em atendimento.")
    if anterior == "emprestado" and estado != anterior:
        b.conflito("O estado do exemplar emprestado é atualizado na devolução.")
    if anterior == "reservado" and estado not in {"reservado", "baixado"}:
        b.conflito("Encerre a reserva antes de alterar o estado do exemplar.")
    if estado == "baixado" and anterior != estado:
        b.baixar_exemplar(db, exemplar, ctx.agora)
    return b.atualizar(
        db, "exemplares", exemplar_id, livro_id=dados.livro_id,
        codigo_tombo=dados.codigo_tombo, estado=estado,
    )


@app.delete("/exemplares/{exemplar_id}", status_code=204)
def excluir_exemplar(exemplar_id: IdRota, ctx: Ctx):
    exemplar = b.obter(ctx.db, "exemplares", exemplar_id)
    if exemplar["estado"] != "baixado":
        b.baixar_exemplar(ctx.db, exemplar, ctx.agora)
    return excluir(ctx, "exemplares", exemplar_id)


@app.post("/emprestimos", status_code=201)
def criar_emprestimo(dados: NovoEmprestimo, ctx: Ctx):
    db = ctx.db
    usuario = b.usuario_publico(db, b.obter(db, "usuarios", dados.usuario_id), ctx.hoje)
    exemplar = b.obter(db, "exemplares", dados.exemplar_id)
    if usuario["situacao"] != "ativo":
        b.conflito("Usuário suspenso.")
    if db.execute(
        "SELECT 1 FROM multas m JOIN emprestimos e ON e.id = m.emprestimo_id "
        "WHERE e.usuario_id = ? AND m.estado = 'aberta'", (dados.usuario_id,),
    ).fetchone():
        b.conflito("O usuário possui multa aberta.")
    limite, prazo, _, _, _ = b.REGRAS[usuario["categoria"]]
    em_aberto = db.execute(
        "SELECT COUNT(*) FROM emprestimos WHERE usuario_id = ? AND data_devolucao IS NULL",
        (dados.usuario_id,),
    ).fetchone()[0]
    if em_aberto >= limite:
        b.conflito("Limite de empréstimos atingido.")
    if exemplar["estado"] == "reservado":
        reserva = db.execute(
            "SELECT id, usuario_id FROM reservas WHERE exemplar_id = ?", (dados.exemplar_id,)
        ).fetchone()
        if reserva["usuario_id"] != dados.usuario_id:
            b.conflito("Exemplar reservado para outro usuário.")
        db.execute("DELETE FROM reservas WHERE id = ?", (reserva["id"],))
    elif exemplar["estado"] != "disponivel":
        b.conflito("Exemplar indisponível para empréstimo.")

    b.atualizar(db, "exemplares", dados.exemplar_id, estado="emprestado")
    emprestimo = b.inserir(db, "emprestimos", {
        **dados.model_dump(),
        "categoria": usuario["categoria"],
        "data_retirada": ctx.hoje.isoformat(),
        "data_prevista": (ctx.hoje + timedelta(days=prazo)).isoformat(),
        "estado": "ativo",
    })
    return b.emprestimo_publico(emprestimo)


@app.post("/emprestimos/{emprestimo_id}/renovar")
def renovar_emprestimo(emprestimo_id: IdRota, ctx: Ctx):
    db = ctx.db
    emprestimo = b.obter(db, "emprestimos", emprestimo_id)
    if emprestimo["estado"] != "ativo":
        b.conflito("A renovação exige um empréstimo ativo e dentro do prazo.")
    _, prazo, renovacoes, _, _ = b.REGRAS[emprestimo["categoria"]]
    if emprestimo["numero_renovacoes"] >= renovacoes:
        b.conflito("Limite de renovações atingido.")
    exemplar = b.obter(db, "exemplares", emprestimo["exemplar_id"])
    if b.fila(db, exemplar["livro_id"]):
        b.conflito("Existe fila de reservas para o livro.")
    prevista = date.fromisoformat(emprestimo["data_prevista"])
    return b.emprestimo_publico(b.atualizar(
        db, "emprestimos", emprestimo_id,
        data_prevista=(prevista + timedelta(days=prazo)).isoformat(),
        numero_renovacoes=emprestimo["numero_renovacoes"] + 1,
    ))


@app.post("/emprestimos/{emprestimo_id}/devolver")
def devolver_emprestimo(emprestimo_id: IdRota, ctx: Ctx):
    db = ctx.db
    emprestimo = b.obter(db, "emprestimos", emprestimo_id)
    if emprestimo["data_devolucao"] is not None:
        b.conflito("Empréstimo já devolvido.")
    exemplar = b.obter(db, "exemplares", emprestimo["exemplar_id"])
    emprestimo = b.atualizar_atraso(db, emprestimo, ctx.hoje, devolvendo=True)
    if emprestimo["dias_atraso"] > 60:
        b.baixar_exemplar(db, exemplar, ctx.agora)
    else:
        b.liberar_exemplar(db, exemplar["id"], ctx.agora)
    return b.emprestimo_publico(emprestimo)


@app.get("/usuarios/{usuario_id}/emprestimos")
def listar_emprestimos(usuario_id: IdRota, ctx: Ctx):
    b.obter(ctx.db, "usuarios", usuario_id)
    return [
        b.emprestimo_publico(emprestimo) for emprestimo in b.listar(
            ctx.db, "SELECT * FROM emprestimos WHERE usuario_id = ? ORDER BY id", (usuario_id,)
        )
    ]


@app.post("/reservas", status_code=201)
def criar_reserva(dados: NovaReserva, ctx: Ctx):
    db = ctx.db
    b.obter(db, "usuarios", dados.usuario_id)
    b.obter(db, "livros", dados.livro_id)
    if not db.execute(
        "SELECT 1 FROM exemplares WHERE livro_id = ? AND estado IN "
        "('disponivel','emprestado','reservado')", (dados.livro_id,),
    ).fetchone():
        b.conflito("O livro não possui exemplar em circulação.")
    reserva = b.inserir(db, "reservas", {
        **dados.model_dump(), "data": ctx.agora.isoformat(), "estado": "aguardando",
    })
    fila = b.fila(db, dados.livro_id)
    return {**reserva, "posicao_fila": len(fila)}


@app.post("/reservas/{reserva_id}/cancelar")
def cancelar_reserva(reserva_id: IdRota, ctx: Ctx):
    reserva = b.obter(ctx.db, "reservas", reserva_id)
    if reserva["estado"] not in {"aguardando", "disponivel"}:
        b.conflito("A reserva já está encerrada.")
    b.encerrar_reserva(ctx.db, reserva, "cancelada", ctx.agora)
    return {**b.obter(ctx.db, "reservas", reserva_id), "posicao_fila": None}


@app.get("/livros/{livro_id}/reservas")
def consultar_fila(livro_id: IdRota, ctx: Ctx):
    b.obter(ctx.db, "livros", livro_id)
    return b.fila(ctx.db, livro_id)


@app.get("/usuarios/{usuario_id}/multas")
def listar_multas(usuario_id: IdRota, ctx: Ctx):
    b.obter(ctx.db, "usuarios", usuario_id)
    return [
        b.multa_publica(multa) for multa in b.listar(
            ctx.db, "SELECT m.* FROM multas m JOIN emprestimos e ON e.id = m.emprestimo_id "
            "WHERE e.usuario_id = ? ORDER BY m.id", (usuario_id,),
        )
    ]


@app.post("/multas/{multa_id}/pagar")
def pagar_multa(multa_id: IdRota, ctx: Ctx):
    multa = b.obter(ctx.db, "multas", multa_id)
    if multa["estado"] != "aberta":
        b.conflito("A multa não está aberta.")
    return b.multa_publica(b.atualizar(
        ctx.db, "multas", multa_id, pago_centavos=multa["valor_centavos"], estado="paga",
    ))


@app.get("/relatorios/livros-mais-emprestados")
def livros_mais_emprestados(inicio: date, fim: date, ctx: Ctx):
    if fim < inicio:
        raise HTTPException(422, "A data final deve ser igual ou posterior à data inicial.")
    return b.listar(
        ctx.db,
        """
        SELECT l.id AS livro_id, l.titulo, COUNT(*) AS total_emprestimos
        FROM emprestimos e
        JOIN exemplares ex ON ex.id = e.exemplar_id
        JOIN livros l ON l.id = ex.livro_id
        WHERE e.data_retirada BETWEEN ? AND ?
        GROUP BY l.id
        ORDER BY total_emprestimos DESC, l.id
        """,
        (inicio.isoformat(), fim.isoformat()),
    )


@app.get("/relatorios/usuarios-com-mais-atrasos")
def usuarios_com_mais_atrasos(ctx: Ctx):
    return b.listar(
        ctx.db,
        """
        SELECT u.id AS usuario_id, u.nome, COUNT(*) AS total_atrasos
        FROM emprestimos e JOIN usuarios u ON u.id = e.usuario_id
        WHERE e.dias_atraso > 0
        GROUP BY u.id
        ORDER BY total_atrasos DESC, u.id
        """,
    )


@app.get("/relatorios/taxa-ocupacao-por-area")
def taxa_ocupacao_por_area(ctx: Ctx):
    return b.listar(
        ctx.db,
        """
        SELECT l.area_conhecimento, COUNT(ex.id) AS total_exemplares,
               SUM(CASE WHEN ex.estado = 'emprestado' THEN 1 ELSE 0 END) AS emprestados,
               COALESCE(ROUND(
                   100.0 * SUM(CASE WHEN ex.estado = 'emprestado' THEN 1 ELSE 0 END)
                   / NULLIF(COUNT(ex.id), 0), 2
               ), 0) AS taxa_ocupacao_percentual
        FROM livros l
        LEFT JOIN exemplares ex ON ex.livro_id = l.id AND ex.estado <> 'baixado'
        GROUP BY l.area_conhecimento
        ORDER BY l.area_conhecimento
        """,
    )
