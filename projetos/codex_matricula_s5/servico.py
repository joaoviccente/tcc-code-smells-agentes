import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from heapq import heapify, heappop, heappush
from pathlib import Path
import sqlite3

from fastapi import HTTPException

REGRAS = {
    # Creditos, trancamentos por disciplina, dias para cancelar
    "graduacao": (28, 2, 15),
    "pos": (16, 1, 30),
    "especial": (8, 0, 7),
}
ORDEM_FILA = """
    ORDER BY CASE a.categoria WHEN 'pos' THEN 1 WHEN 'graduacao' THEN 2 ELSE 3 END,
             m.data, m.id
"""


def agora():
    return datetime.now(UTC)


@contextmanager
def transacao(caminho):
    db = sqlite3.connect(caminho, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def inicializar(caminho):
    with transacao(caminho) as db:
        db.executescript(Path(__file__).with_name("esquema.sql").read_text(encoding="utf-8"))


def conflito(mensagem):
    raise HTTPException(409, mensagem)


def obter(db, tabela, id):
    linha = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id,)).fetchone()
    if linha is None:
        raise HTTPException(404, f"Registro inexistente em {tabela}")
    return linha


def serializar(linha):
    dados = dict(linha)
    if "horario" in dados:
        dados["horario"] = json.loads(dados["horario"])
    return dados


def total(db, sql, params):
    return db.execute(sql, params).fetchone()[0]


def fila(db, turma_id, estado="lista_de_espera"):
    return db.execute(
        """SELECT m.* FROM matriculas m JOIN alunos a ON a.id = m.aluno_id
           WHERE m.turma_id = ? AND m.estado = ?""" + ORDEM_FILA,
        (turma_id, estado),
    ).fetchall()


def contar_ocupadas(db, turma_id):
    return total(db, """SELECT COUNT(*) FROM matriculas
                        WHERE turma_id = ? AND estado IN ('confirmada', 'solicitada')""",
                 (turma_id,))


def verificar_elegibilidade(db, aluno, turma):
    if aluno["situacao"] != "ativo":
        conflito("Somente alunos ativos podem se matricular")
    disciplina_id = turma["disciplina_id"]
    aluno_id = aluno["id"]
    if total(db, """
        SELECT COUNT(*) FROM pre_requisitos p WHERE p.disciplina_id = ?
        AND NOT EXISTS (SELECT 1 FROM historico h WHERE h.disciplina_id = p.exigida_id
                        AND h.aluno_id = ? AND h.situacao = 'aprovado')
    """, (disciplina_id, aluno_id)):
        conflito("Pre-requisitos pendentes")
    if total(db, """
        SELECT COUNT(*) FROM historico WHERE aluno_id = ? AND disciplina_id = ?
        AND situacao = 'reprovado'
    """, (aluno_id, disciplina_id)) >= 3:
        conflito("Limite de reprovacoes atingido")
    confirmadas = db.execute("""
        SELECT d.creditos, t.horario FROM matriculas m JOIN turmas t ON t.id = m.turma_id
        JOIN disciplinas d ON d.id = t.disciplina_id
        WHERE m.aluno_id = ? AND m.estado = 'confirmada' AND t.semestre = ?
    """, (aluno_id, turma["semestre"])).fetchall()
    creditos = obter(db, "disciplinas", disciplina_id)["creditos"]
    if creditos + sum(linha["creditos"] for linha in confirmadas) > REGRAS[aluno["categoria"]][0]:
        conflito("Limite de creditos do semestre excedido")
    horarios = json.loads(turma["horario"])
    for linha in confirmadas:
        if any(a["dia"] == b["dia"] and a["inicio"] < b["fim"] and b["inicio"] < a["fim"]
               for a in horarios for b in json.loads(linha["horario"])):
            conflito("Conflito de horario com matricula confirmada")


def alterar_matricula(db, matricula_id, estado, instante=None, prazo=None):
    db.execute("""
        UPDATE matriculas SET estado = ?, prazo_confirmacao = ?,
        confirmada_em = COALESCE(?, confirmada_em) WHERE id = ?
    """, (estado, prazo and prazo.isoformat(), instante and instante.isoformat(), matricula_id))


def atualizar_fila(db, turma_id, instante):
    turma = obter(db, "turmas", turma_id)
    if turma["estado"] not in ("aberta", "lotada"):
        return
    reservas = db.execute("""
        SELECT id, prazo_confirmacao FROM matriculas
        WHERE turma_id = ? AND estado = 'solicitada' AND prazo_confirmacao <= ?
        ORDER BY prazo_confirmacao, id
    """, (turma_id, instante.isoformat())).fetchall()
    liberacoes = [datetime.fromisoformat(reserva["prazo_confirmacao"]) for reserva in reservas]
    for reserva in reservas:
        alterar_matricula(db, reserva["id"], "cancelada")
    vagas_livres = turma["vagas"] - contar_ocupadas(db, turma_id)
    vagas_imediatas = vagas_livres - len(liberacoes)
    heapify(liberacoes)
    for candidato in fila(db, turma_id):
        if not liberacoes and vagas_imediatas <= 0:
            break
        aluno = obter(db, "alunos", candidato["aluno_id"])
        try:
            verificar_elegibilidade(db, aluno, turma)
        except HTTPException as erro:
            if erro.status_code != 409:
                raise
            alterar_matricula(db, candidato["id"], "cancelada")
            continue
        if liberacoes:
            liberada_em = heappop(liberacoes)
        else:
            liberada_em = instante
            vagas_imediatas -= 1
        inicio = max(liberada_em, datetime.fromisoformat(candidato["data"]))
        prazo = inicio + timedelta(hours=48)
        if prazo <= instante:
            alterar_matricula(db, candidato["id"], "cancelada")
            heappush(liberacoes, prazo)
        else:
            alterar_matricula(db, candidato["id"], "solicitada", prazo=prazo)
    estado = "lotada" if contar_ocupadas(db, turma_id) >= turma["vagas"] else "aberta"
    db.execute("UPDATE turmas SET estado = ? WHERE id = ? AND estado <> ?", (estado, turma_id, estado))


def expirar_reservas(db, instante):
    turmas = db.execute("""
        SELECT DISTINCT turma_id FROM matriculas
        WHERE estado = 'solicitada' AND prazo_confirmacao <= ?
    """, (instante.isoformat(),)).fetchall()
    for linha in turmas:
        atualizar_fila(db, linha["turma_id"], instante)


def fechar_turma(db, turma_id, estado):
    filtro = "estado <> 'cancelada'" if estado == "cancelada" else (
        "estado IN ('solicitada', 'lista_de_espera')"
    )
    db.execute(f"""
        UPDATE matriculas SET estado = 'cancelada', prazo_confirmacao = NULL
        WHERE turma_id = ? AND {filtro}
    """, (turma_id,))
    db.execute("UPDATE turmas SET estado = ? WHERE id = ?", (estado, turma_id))


def registrar_evento(db, matricula, turma, situacao, motivo):
    db.execute("""
        INSERT INTO historico (aluno_id, disciplina_id, semestre, situacao, motivo, matricula_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (matricula["aluno_id"], turma["disciplina_id"], turma["semestre"],
          situacao, motivo, matricula["id"]))


def encerrar_matricula(db, matricula, trancar, instante):
    estados = ("confirmada",) if trancar else ("confirmada", "solicitada", "lista_de_espera")
    if matricula["estado"] not in estados:
        conflito("Estado da matricula incompativel com a operacao")
    aluno = obter(db, "alunos", matricula["aluno_id"])
    turma = obter(db, "turmas", matricula["turma_id"])
    _, limite, dias = REGRAS[aluno["categoria"]]
    afetadas = {turma["id"]}
    if matricula["estado"] == "confirmada":
        prazo = datetime.fromisoformat(matricula["confirmada_em"]) + timedelta(days=dias)
        if trancar:
            if instante > prazo:
                conflito("Prazo de trancamento expirado")
            anteriores = total(db, """
                SELECT COUNT(*) FROM historico WHERE aluno_id = ? AND disciplina_id = ?
                AND situacao = 'trancado'
            """, (aluno["id"], turma["disciplina_id"]))
            if anteriores >= limite:
                conflito("Limite de trancamentos da disciplina atingido")
            registrar_evento(db, matricula, turma, "trancado", "trancamento")
        elif instante > prazo:
            registrar_evento(db, matricula, turma, "reprovado", "reprovacao_por_falta")
    alterar_matricula(db, matricula["id"], "trancada" if trancar else "cancelada")
    if trancar:
        afetadas.update(aplicar_trancamento_do_aluno(db, aluno["id"], turma["semestre"]))
    for turma_id in sorted(afetadas):
        atualizar_fila(db, turma_id, instante)


def aplicar_trancamento_do_aluno(db, aluno_id, semestre):
    if total(db, """
        SELECT COUNT(*) FROM historico WHERE aluno_id = ? AND semestre = ? AND situacao = 'trancado'
    """, (aluno_id, semestre)) < 3:
        return set()
    db.execute("UPDATE alunos SET situacao = 'trancado' WHERE id = ? AND situacao = 'ativo'", (aluno_id,))
    afetadas = {linha["turma_id"] for linha in db.execute("""
        SELECT turma_id FROM matriculas WHERE aluno_id = ? AND estado = 'confirmada'
    """, (aluno_id,))}
    db.execute("""
        UPDATE matriculas SET estado = 'cancelada' WHERE aluno_id = ? AND estado = 'confirmada'
    """, (aluno_id,))
    return afetadas
