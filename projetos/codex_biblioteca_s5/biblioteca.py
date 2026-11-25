import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from fastapi import HTTPException

RAIZ = Path(__file__).resolve().parent
BANCO = os.environ.get("BIBLIOTECA_DB", RAIZ / "biblioteca.db")


class Politica(NamedTuple):
    limite: int
    prazo: int
    renovacoes: int
    centavos_por_dia: int
    teto: int


POLITICAS = {
    "aluno": Politica(3, 7, 2, 100, 3000),
    "professor": Politica(8, 30, 4, 50, 5000),
    "visitante": Politica(1, 3, 0, 200, 2000),
}


def relogio():
    return datetime.now(timezone.utc)


def dia_local(agora):
    return agora.astimezone().date()


def conectar():
    db = sqlite3.connect(BANCO, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def inicializar():
    db = conectar()
    try:
        db.executescript((RAIZ / "schema.sql").read_text(encoding="ascii"))
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


def obter(db, tabela, id):
    registro = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id,)).fetchone()
    if registro is None:
        raise HTTPException(404, "Registro nao encontrado")
    return dict(registro)


def exigir(condicao, mensagem):
    if not condicao:
        raise HTTPException(409, mensagem)


def usuario_publico(usuario, hoje):
    usuario = dict(usuario)
    ate = usuario["suspenso_ate"]
    manual = usuario.pop("situacao_manual")
    usuario["situacao"] = "suspenso" if manual == "suspenso" or (ate and ate > hoje.isoformat()) else "ativo"
    return usuario


def distribuir(db, livro_id, agora):
    livres = db.execute(
        "SELECT id FROM exemplares WHERE livro_id = ? AND estado = 'disponivel' ORDER BY id",
        (livro_id,),
    ).fetchall()
    fila = db.execute(
        "SELECT id FROM reservas WHERE livro_id = ? AND estado = 'aguardando' ORDER BY id",
        (livro_id,),
    ).fetchall()
    expira = (agora + timedelta(hours=48)).isoformat()
    for exemplar, reserva in zip(livres, fila):
        db.execute("UPDATE exemplares SET estado = 'reservado' WHERE id = ?", (exemplar["id"],))
        db.execute(
            "UPDATE reservas SET estado = 'disponivel', exemplar_id = ?, expira_em = ? WHERE id = ?",
            (exemplar["id"], expira, reserva["id"]),
        )


def liberar_reserva(db, reserva, estado):
    db.execute("UPDATE reservas SET estado = ? WHERE id = ?", (estado, reserva["id"]))
    if reserva["exemplar_id"] is not None:
        db.execute(
            "UPDATE exemplares SET estado = 'disponivel' WHERE id = ? AND estado = 'reservado'",
            (reserva["exemplar_id"],),
        )


def cancelar_reservas_se_baixa(db, livro_id, era_disponivel=False):
    estados = "'disponivel'" if era_disponivel else "'disponivel', 'reservado', 'emprestado'"
    estoque = db.execute(
        f"SELECT 1 FROM exemplares WHERE livro_id = ? AND estado IN ({estados}) LIMIT 1",
        (livro_id,),
    ).fetchone()
    if estoque is None:
        reservas = db.execute(
            "SELECT * FROM reservas WHERE livro_id = ? AND estado IN ('aguardando', 'disponivel')",
            (livro_id,),
        ).fetchall()
        for reserva in reservas:
            liberar_reserva(db, reserva, "cancelada")


def fila_reservas(db, livro_id):
    fila = db.execute(
        """SELECT * FROM reservas WHERE livro_id = ? AND estado IN ('aguardando', 'disponivel')
           ORDER BY id""",
        (livro_id,),
    )
    return [dict(reserva) | {"posicao_fila": posicao} for posicao, reserva in enumerate(fila, 1)]


def reserva_publica(db, id):
    reserva = obter(db, "reservas", id)
    return next(
        (item for item in fila_reservas(db, reserva["livro_id"]) if item["id"] == id),
        reserva | {"posicao_fila": None},
    )


def dias_atraso(emprestimo, hoje):
    return max(0, (hoje - date.fromisoformat(emprestimo["data_prevista"])).days)


def atualizar_multa(db, emprestimo, atraso, baixado=False):
    if atraso == 0:
        return
    categoria = emprestimo["categoria"]
    politica = POLITICAS[categoria]
    valor = politica.teto if baixado else min(atraso * politica.centavos_por_dia, politica.teto)
    estado = "perdoada" if categoria == "professor" and atraso <= 2 else "aberta"
    db.execute(
        """INSERT INTO multas (emprestimo_id, centavos, estado) VALUES (?, ?, ?)
           ON CONFLICT(emprestimo_id) DO UPDATE SET centavos = excluded.centavos,
           estado = CASE WHEN excluded.estado = 'perdoada' THEN 'perdoada'
                         WHEN multas.centavos_pagos >= excluded.centavos THEN 'paga'
                         ELSE 'aberta' END
           WHERE multas.centavos <> excluded.centavos""",
        (emprestimo["id"], valor, estado),
    )


def sincronizar(db, agora, hoje):
    while True:
        reserva = db.execute(
            """SELECT * FROM reservas WHERE estado = 'disponivel' AND expira_em <= ?
               ORDER BY expira_em, id LIMIT 1""",
            (agora.isoformat(),),
        ).fetchone()
        if reserva is None:
            break
        liberar_reserva(db, reserva, "expirada")
        distribuir(db, reserva["livro_id"], datetime.fromisoformat(reserva["expira_em"]))

    atrasados = db.execute(
        "SELECT * FROM emprestimos WHERE data_devolucao IS NULL AND data_prevista < ?",
        (hoje.isoformat(),),
    ).fetchall()
    for emprestimo in atrasados:
        atraso = dias_atraso(emprestimo, hoje)
        if emprestimo["estado"] != "atrasado":
            db.execute("UPDATE emprestimos SET estado = 'atrasado' WHERE id = ?", (emprestimo["id"],))
        atualizar_multa(db, emprestimo, atraso)
        if atraso > 15:
            ate = (hoje + timedelta(days=2 * atraso)).isoformat()
            db.execute(
                """UPDATE usuarios SET suspenso_ate = ? WHERE id = ?
                   AND (suspenso_ate IS NULL OR suspenso_ate < ?)""",
                (ate, emprestimo["usuario_id"], ate),
            )


def multa_publica(registro):
    multa = dict(registro)
    centavos = multa.pop("centavos")
    pagos = multa.pop("centavos_pagos")
    multa["valor"] = centavos / 100
    multa["saldo"] = (centavos - pagos) / 100 if multa["estado"] == "aberta" else 0
    return multa
