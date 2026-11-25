import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from fastapi import HTTPException

BASE = Path(__file__).resolve().parent


class Regra(NamedTuple):
    creditos: int
    trancamentos: int
    dias: int


REGRAS = {
    "graduacao": Regra(28, 2, 15),
    "pos": Regra(16, 1, 30),
    "especial": Regra(8, 0, 7),
}


def agora():
    return datetime.now(timezone.utc)


def conectar():
    db = sqlite3.connect(os.environ.get("MATRICULAS_DB", str(BASE / "matriculas.sqlite3")))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def inicializar():
    with conectar() as db:
        db.executescript((BASE / "esquema.sql").read_text(encoding="ascii"))
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


def buscar(db, tabela, item_id):
    item = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        raise HTTPException(404, "Registro nao encontrado")
    return dict(item)


def exigir(condicao, mensagem):
    if not condicao:
        raise HTTPException(409, mensagem)


def ocupacao(db, turma_id):
    return db.execute(
        """SELECT COUNT(CASE WHEN estado = 'confirmada' THEN 1 END) AS confirmadas,
                  COUNT(CASE WHEN estado = 'solicitada' THEN 1 END) AS reservadas
           FROM matriculas WHERE turma_id = ?""",
        (turma_id,),
    ).fetchone()


def fila(db, turma_id):
    return db.execute(
        """SELECT m.* FROM matriculas m JOIN alunos a ON a.id = m.aluno_id
           WHERE m.turma_id = ? AND m.estado = 'lista_de_espera'
           ORDER BY CASE a.categoria WHEN 'pos' THEN 1 WHEN 'graduacao' THEN 2 ELSE 3 END,
                    m.data, m.id""",
        (turma_id,),
    ).fetchall()


def elegivel(db, aluno, turma):
    aluno_id = aluno["id"]
    disciplina_id = turma["disciplina_id"]
    semestre = turma["semestre"]
    regra = REGRAS[aluno["categoria"]]
    exigir(aluno["situacao"] == "ativo", "Somente alunos ativos podem se matricular")
    faltante = db.execute(
        """SELECT 1 FROM pre_requisitos p WHERE disciplina_id = ? AND NOT EXISTS (
               SELECT 1 FROM historico h WHERE h.aluno_id = ? AND h.disciplina_id = p.exigida_id
                 AND h.situacao = 'aprovado' AND h.semestre <= ?
           )""",
        (disciplina_id, aluno_id, semestre),
    ).fetchone()
    exigir(faltante is None, "Pre-requisitos pendentes")
    reprovacoes = db.execute(
        """SELECT COUNT(*) FROM historico WHERE aluno_id = ? AND disciplina_id = ?
           AND situacao = 'reprovado'""",
        (aluno_id, disciplina_id),
    ).fetchone()[0]
    exigir(reprovacoes < 3, "Limite de reprovacoes atingido")
    confirmadas = db.execute(
        """SELECT t.*, d.creditos FROM matriculas m JOIN turmas t ON t.id = m.turma_id
           JOIN disciplinas d ON d.id = t.disciplina_id
           WHERE m.aluno_id = ? AND m.estado = 'confirmada' AND t.semestre = ?""",
        (aluno_id, semestre),
    ).fetchall()
    creditos = buscar(db, "disciplinas", disciplina_id)["creditos"]
    exigir(sum(item["creditos"] for item in confirmadas) + creditos <= regra.creditos,
           "Limite de creditos do semestre excedido")
    for item in confirmadas:
        conflito = (
            item["dia"] == turma["dia"]
            and item["inicio"] < turma["fim"]
            and turma["inicio"] < item["fim"]
        )
        exigir(not conflito, "Conflito de horario")


def cancelar_registros(db, condicao, valores):
    db.execute(
        f"UPDATE matriculas SET estado = 'cancelada', oferta_ate = NULL WHERE {condicao}",
        valores,
    )


def atualizar_fila(db, turma_id, instante):
    turma = buscar(db, "turmas", turma_id)
    if turma["estado"] not in ("aberta", "lotada"):
        return
    cancelar_registros(db, "turma_id = ? AND estado = 'solicitada' AND oferta_ate <= ?",
                       (turma_id, instante.isoformat()))
    confirmadas, reservadas = ocupacao(db, turma_id)
    livres = turma["vagas"] - confirmadas - reservadas
    if livres > 0:
        prazo = (instante + timedelta(hours=48)).isoformat()
        for candidato in fila(db, turma_id):
            try:
                elegivel(db, buscar(db, "alunos", candidato["aluno_id"]), turma)
            except HTTPException as erro:
                if erro.status_code != 409:
                    raise
                cancelar_registros(db, "id = ?", (candidato["id"],))
                continue
            db.execute("UPDATE matriculas SET estado = 'solicitada', oferta_ate = ? WHERE id = ?",
                       (prazo, candidato["id"]))
            livres -= 1
            if livres == 0:
                break
    estado = "lotada" if livres == 0 else "aberta"
    db.execute("UPDATE turmas SET estado = ? WHERE id = ?", (estado, turma_id))


def expirar_ofertas(db, instante):
    turmas = db.execute(
        "SELECT DISTINCT turma_id FROM matriculas WHERE estado = 'solicitada' AND oferta_ate <= ?",
        (instante.isoformat(),),
    ).fetchall()
    for turma in turmas:
        atualizar_fila(db, turma["turma_id"], instante)


def solicitar(db, dados, instante):
    aluno = buscar(db, "alunos", dados.aluno_id)
    turma = buscar(db, "turmas", dados.turma_id)
    exigir(turma["estado"] in ("aberta", "lotada"), "Turma indisponivel")
    exigir(db.execute("SELECT 1 FROM periodos_encerrados WHERE semestre = ?",
                      (turma["semestre"],)).fetchone() is None, "Periodo de matricula encerrado")
    elegivel(db, aluno, turma)
    imediato = turma["estado"] == "aberta"
    data = instante.isoformat()
    cursor = db.execute(
        """INSERT INTO matriculas (aluno_id, turma_id, data, estado, confirmada_em)
           VALUES (?, ?, ?, ?, ?)""",
        (dados.aluno_id, dados.turma_id, data,
         "confirmada" if imediato else "lista_de_espera", data if imediato else None),
    )
    atualizar_fila(db, dados.turma_id, instante)
    return buscar(db, "matriculas", cursor.lastrowid)


def confirmar(db, matricula_id, instante):
    matricula = buscar(db, "matriculas", matricula_id)
    if matricula["estado"] == "confirmada":
        return matricula
    exigir(matricula["estado"] == "solicitada", "Matricula sem oferta de vaga vigente")
    exigir(instante < datetime.fromisoformat(matricula["oferta_ate"]), "Oferta de vaga expirada")
    turma = buscar(db, "turmas", matricula["turma_id"])
    elegivel(db, buscar(db, "alunos", matricula["aluno_id"]), turma)
    db.execute(
        """UPDATE matriculas SET estado = 'confirmada', oferta_ate = NULL, confirmada_em = ?
           WHERE id = ?""",
        (instante.isoformat(), matricula_id),
    )
    return buscar(db, "matriculas", matricula_id)


def aplicar_trancamento_semestral(db, aluno_id, semestre):
    total = db.execute(
        """SELECT COUNT(*) FROM historico WHERE aluno_id = ? AND semestre = ?
           AND situacao = 'trancado'""",
        (aluno_id, semestre),
    ).fetchone()[0]
    if total < 3:
        return set()
    db.execute("UPDATE alunos SET situacao = 'trancado' WHERE id = ?", (aluno_id,))
    filtro = "aluno_id = ? AND estado IN ('confirmada', 'solicitada', 'lista_de_espera')"
    afetadas = {row["turma_id"] for row in db.execute(
        f"SELECT turma_id FROM matriculas WHERE {filtro}", (aluno_id,),
    )}
    cancelar_registros(db, filtro, (aluno_id,))
    return afetadas


def desligar(db, matricula_id, instante, trancar=False):
    matricula = buscar(db, "matriculas", matricula_id)
    turma = buscar(db, "turmas", matricula["turma_id"])
    aluno = buscar(db, "alunos", matricula["aluno_id"])
    exigir(turma["estado"] in ("aberta", "lotada"), "Turma indisponivel")
    exigir(matricula["estado"] in ("confirmada", "solicitada", "lista_de_espera"),
           "Matricula inativa")
    confirmada = matricula["estado"] == "confirmada"
    regra = REGRAS[aluno["categoria"]]
    no_prazo = confirmada and instante <= (
        datetime.fromisoformat(matricula["confirmada_em"]) + timedelta(days=regra.dias)
    )
    if trancar:
        exigir(no_prazo, "Trancamento exige matricula confirmada dentro do prazo")
        total = db.execute(
            """SELECT COUNT(*) FROM historico WHERE aluno_id = ? AND disciplina_id = ?
               AND situacao = 'trancado'""",
            (aluno["id"], turma["disciplina_id"]),
        ).fetchone()[0]
        exigir(total < regra.trancamentos, "Limite de trancamentos da disciplina atingido")

    db.execute("UPDATE matriculas SET estado = ?, oferta_ate = NULL WHERE id = ?",
               ("trancada" if trancar else "cancelada", matricula_id))
    if trancar or (confirmada and not no_prazo):
        db.execute(
            """INSERT INTO historico (aluno_id, disciplina_id, semestre, situacao, motivo, matricula_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (aluno["id"], turma["disciplina_id"], turma["semestre"],
             "trancado" if trancar else "reprovado", "falta" if not trancar else None, matricula_id),
        )
    afetadas = {turma["id"]}
    if trancar:
        afetadas.update(aplicar_trancamento_semestral(db, aluno["id"], turma["semestre"]))
    for turma_id in afetadas:
        atualizar_fila(db, turma_id, instante)
    return buscar(db, "matriculas", matricula_id)
