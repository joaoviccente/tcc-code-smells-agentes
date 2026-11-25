from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import os
import sqlite3

from fastapi import HTTPException


REGRAS = {
    # Limite, prazo, renovacoes, centavos por dia, teto em centavos.
    "aluno": (3, 7, 2, 100, 3000),
    "professor": (8, 30, 4, 50, 5000),
    "visitante": (1, 3, 0, 200, 2000),
}
FUSO_BIBLIOTECA = timezone(timedelta(hours=-3))
SCHEMA = Path(__file__).with_name("schema.sql")


def agora_utc():
    return datetime.now(timezone.utc)


def conectar():
    caminho = os.environ.get(
        "BIBLIOTECA_DB", str(Path(__file__).with_name("biblioteca.sqlite3"))
    )
    db = sqlite3.connect(caminho, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def inicializar():
    db = conectar()
    try:
        db.executescript(SCHEMA.read_text(encoding="utf-8-sig"))
    finally:
        db.close()


@contextmanager
def transacao():
    db = conectar()
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            yield db
    finally:
        db.close()


def listar(db, sql, parametros=()):
    return [dict(row) for row in db.execute(sql, parametros)]


def obter(db, tabela, registro_id):
    row = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (registro_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Registro não encontrado.")
    return dict(row)


def conflito(mensagem):
    raise HTTPException(409, mensagem)


def inserir(db, tabela, dados):
    colunas = ", ".join(dados)
    parametros = ", ".join("?" for _ in dados)
    cursor = db.execute(
        f"INSERT INTO {tabela} ({colunas}) VALUES ({parametros})", tuple(dados.values())
    )
    return obter(db, tabela, cursor.lastrowid)


def atualizar(db, tabela, registro_id, **dados):
    if dados:
        colunas = ", ".join(f"{coluna} = ?" for coluna in dados)
        db.execute(
            f"UPDATE {tabela} SET {colunas} WHERE id = ?",
            (*dados.values(), registro_id),
        )
    return obter(db, tabela, registro_id)


def usuario_publico(db, usuario, hoje):
    suspensao = db.execute(
        "SELECT MAX(suspenso_ate) FROM emprestimos WHERE usuario_id = ? "
        "AND suspenso_ate > ?",
        (usuario["id"], hoje.isoformat()),
    ).fetchone()[0]
    return {
        **usuario,
        "situacao": "suspenso" if suspensao else usuario["situacao"],
        "suspenso_ate": suspensao,
    }


def emprestimo_publico(emprestimo):
    return {
        chave: valor for chave, valor in emprestimo.items()
        if chave not in {"categoria", "suspenso_ate"}
    }


def multa_publica(multa):
    return {
        "id": multa["id"],
        "emprestimo_id": multa["emprestimo_id"],
        "valor": multa["valor_centavos"] / 100,
        "saldo": (
            (multa["valor_centavos"] - multa["pago_centavos"]) / 100
            if multa["estado"] == "aberta" else 0
        ),
        "estado": multa["estado"],
    }


def atualizar_atraso(db, emprestimo, hoje, devolvendo=False):
    prevista = date.fromisoformat(emprestimo["data_prevista"])
    atraso = max(0, (hoje - prevista).days)
    if not devolvendo and atraso == emprestimo["dias_atraso"]:
        return emprestimo

    suspenso_ate = hoje + timedelta(days=2 * atraso) if atraso > 15 else None
    emprestimo = atualizar(
        db, "emprestimos", emprestimo["id"],
        estado="devolvido" if devolvendo else ("atrasado" if atraso else "ativo"),
        data_devolucao=hoje.isoformat() if devolvendo else None,
        dias_atraso=atraso,
        suspenso_ate=suspenso_ate.isoformat() if suspenso_ate else None,
    )
    if atraso:
        categoria = emprestimo["categoria"]
        _, _, _, diaria, teto = REGRAS[categoria]
        valor = teto if devolvendo and atraso > 60 else min(atraso * diaria, teto)
        perdoada = categoria == "professor" and atraso <= 2
        db.execute(
            """
            INSERT INTO multas (emprestimo_id, valor_centavos, estado) VALUES (?, ?, ?)
            ON CONFLICT(emprestimo_id) DO UPDATE SET
                valor_centavos = excluded.valor_centavos,
                estado = CASE
                    WHEN excluded.estado = 'perdoada' THEN 'perdoada'
                    WHEN multas.pago_centavos >= excluded.valor_centavos THEN 'paga'
                    ELSE 'aberta'
                END
            """,
            (emprestimo["id"], valor, "perdoada" if perdoada else "aberta"),
        )
    return emprestimo


def liberar_exemplar(db, exemplar_id, agora):
    exemplar = obter(db, "exemplares", exemplar_id)
    proxima = db.execute(
        "SELECT id FROM reservas WHERE livro_id = ? AND estado = 'aguardando' "
        "ORDER BY id LIMIT 1",
        (exemplar["livro_id"],),
    ).fetchone()
    if proxima:
        atualizar(
            db, "reservas", proxima["id"], estado="disponivel",
            exemplar_id=exemplar_id, expira_em=(agora + timedelta(hours=48)).isoformat(),
        )
    atualizar(db, "exemplares", exemplar_id, estado="reservado" if proxima else "disponivel")


def encerrar_reserva(db, reserva, estado, agora):
    atualizar(db, "reservas", reserva["id"], estado=estado, exemplar_id=None, expira_em=None)
    if reserva["exemplar_id"] is not None:
        liberar_exemplar(db, reserva["exemplar_id"], agora)


def baixar_exemplar(db, exemplar, agora):
    livro_id = exemplar["livro_id"]
    exemplar_id = exemplar["id"]
    atualizado = atualizar(db, "exemplares", exemplar_id, estado="baixado")
    outros = listar(
        db, "SELECT estado FROM exemplares WHERE livro_id = ? AND id <> ?",
        (livro_id, exemplar_id),
    )
    estados = {outro["estado"] for outro in outros}
    ultimo_disponivel = exemplar["estado"] == "disponivel" and "disponivel" not in estados
    if ultimo_disponivel or not (estados & {"disponivel", "reservado", "emprestado"}):
        db.execute(
            "UPDATE exemplares SET estado = 'disponivel' "
            "WHERE livro_id = ? AND estado = 'reservado'", (livro_id,)
        )
        db.execute(
            "UPDATE reservas SET estado = 'cancelada', exemplar_id = NULL, expira_em = NULL "
            "WHERE livro_id = ? AND estado IN ('aguardando','disponivel')", (livro_id,)
        )
    elif exemplar["estado"] == "reservado":
        reserva = db.execute(
            "SELECT id FROM reservas WHERE exemplar_id = ?", (exemplar_id,)
        ).fetchone()
        atualizar(db, "reservas", reserva["id"], estado="aguardando", exemplar_id=None, expira_em=None)
        for disponivel in listar(
            db, "SELECT id FROM exemplares WHERE livro_id = ? AND estado = 'disponivel' ORDER BY id",
            (livro_id,),
        ):
            liberar_exemplar(db, disponivel["id"], agora)
    return atualizado


def sincronizar(db, agora):
    hoje = agora.astimezone(FUSO_BIBLIOTECA).date()
    for emprestimo in listar(
        db, "SELECT * FROM emprestimos WHERE data_devolucao IS NULL AND data_prevista < ?",
        (hoje.isoformat(),),
    ):
        atualizar_atraso(db, emprestimo, hoje)
    for reserva in listar(
        db, "SELECT * FROM reservas WHERE estado = 'disponivel' AND expira_em <= ? "
        "ORDER BY expira_em, id",
        (agora.isoformat(),),
    ):
        encerrar_reserva(db, reserva, "expirada", agora)
    return hoje


def fila(db, livro_id):
    reservas = listar(
        db, "SELECT * FROM reservas WHERE livro_id = ? "
        "AND estado IN ('aguardando','disponivel') ORDER BY id", (livro_id,),
    )
    return [
        {**reserva, "posicao_fila": posicao}
        for posicao, reserva in enumerate(reservas, start=1)
    ]
