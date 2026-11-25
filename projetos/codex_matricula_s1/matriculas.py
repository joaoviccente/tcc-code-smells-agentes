import json
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from banco import transacao
from modelos import Horario

LIMITES = {
    "graduacao": (28, 2, 15),
    "pos": (16, 1, 30),
    "especial": (8, 0, 7),
}


def agora():
    return datetime.now(UTC)


def erro(status, mensagem):
    raise HTTPException(status, mensagem)


def obter(db, tabela, id):
    linha = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id,)).fetchone()
    if linha is None:
        erro(404, "Registro não encontrado")
    return linha


def quantidade(db, consulta, parametros):
    return db.execute(consulta, parametros).fetchone()[0]


def fila(db, turma_id):
    return db.execute("""
        SELECT m.* FROM matriculas m JOIN alunos a ON a.id = m.aluno_id
        WHERE m.turma_id = ? AND m.estado = 'lista_de_espera'
        ORDER BY (m.oferta_expira_em IS NOT NULL) DESC,
            CASE a.categoria WHEN 'pos' THEN 1 WHEN 'graduacao' THEN 2 ELSE 3 END,
            m.data, m.id
    """, (turma_id,)).fetchall()


def atualizar_fila(db, turma_id, instante):
    turma = obter(db, "turmas", turma_id)
    if turma["estado"] in ("cancelada", "encerrada"):
        return
    db.execute("""
        UPDATE matriculas SET estado = 'cancelada', oferta_expira_em = NULL
        WHERE turma_id = ? AND estado = 'lista_de_espera' AND oferta_expira_em <= ?
    """, (turma_id, instante.isoformat()))
    ocupadas = quantidade(db, """
        SELECT count(*) FROM matriculas WHERE turma_id = ?
        AND (estado = 'confirmada' OR (estado = 'lista_de_espera' AND oferta_expira_em IS NOT NULL))
    """, (turma_id,))
    for item in fila(db, turma_id):
        if ocupadas >= turma["vagas"]:
            break
        if item["oferta_expira_em"] is not None:
            continue
        db.execute("UPDATE matriculas SET oferta_expira_em = ? WHERE id = ?",
                   ((instante + timedelta(hours=48)).isoformat(), item["id"]))
        ocupadas += 1
    db.execute("UPDATE turmas SET estado = ? WHERE id = ?",
               ("lotada" if ocupadas >= turma["vagas"] else "aberta", turma_id))


def expirar_ofertas():
    with transacao() as db:
        instante = agora()
        turmas = db.execute("""
            SELECT DISTINCT turma_id FROM matriculas
            WHERE estado = 'lista_de_espera' AND oferta_expira_em <= ?
        """, (instante.isoformat(),)).fetchall()
        for turma in turmas:
            atualizar_fila(db, turma["turma_id"], instante)


def validar_matricula(db, aluno, turma):
    if aluno["situacao"] != "ativo":
        erro(409, "Aluno precisa estar ativo")
    if turma["estado"] in ("cancelada", "encerrada"):
        erro(409, "Turma indisponível")
    if quantidade(db, """
        SELECT count(*) FROM prerequisitos p WHERE p.disciplina_id = ? AND NOT EXISTS (
            SELECT 1 FROM historico h WHERE h.aluno_id = ?
            AND h.disciplina_id = p.disciplina_exigida_id AND h.situacao = 'aprovado'
        )
    """, (turma["disciplina_id"], aluno["id"])):
        erro(409, "Há pré-requisitos sem aprovação")
    if quantidade(db, """
        SELECT count(*) FROM historico WHERE aluno_id = ? AND disciplina_id = ? AND situacao = 'reprovado'
    """, (aluno["id"], turma["disciplina_id"])) >= 3:
        erro(409, "Aluno já acumula três reprovações na disciplina")
    confirmadas = db.execute("""
        SELECT d.creditos, t.horario FROM matriculas m JOIN turmas t ON t.id = m.turma_id
        JOIN disciplinas d ON d.id = t.disciplina_id
        WHERE m.aluno_id = ? AND t.semestre = ? AND m.estado = 'confirmada'
    """, (aluno["id"], turma["semestre"])).fetchall()
    creditos = obter(db, "disciplinas", turma["disciplina_id"])["creditos"]
    if creditos + sum(item["creditos"] for item in confirmadas) > LIMITES[aluno["categoria"]][0]:
        erro(409, "Limite de créditos do semestre excedido")
    horarios = [Horario.model_validate(item) for item in json.loads(turma["horario"])]
    for item in confirmadas:
        for existente in map(Horario.model_validate, json.loads(item["horario"])):
            if any(h.dia == existente.dia and h.inicio < existente.fim and existente.inicio < h.fim for h in horarios):
                erro(409, "Horário em conflito com matrícula confirmada")


def solicitar(db, aluno_id, turma_id, instante):
    aluno = obter(db, "alunos", aluno_id)
    turma = obter(db, "turmas", turma_id)
    if db.execute("SELECT 1 FROM periodos_encerrados WHERE semestre = ?", (turma["semestre"],)).fetchone():
        erro(409, "Período de matrícula encerrado")
    if quantidade(db, """
        SELECT count(*) FROM matriculas WHERE aluno_id = ? AND turma_id = ?
        AND estado IN ('solicitada', 'confirmada', 'lista_de_espera')
    """, (aluno_id, turma_id)):
        erro(409, "Aluno já possui matrícula vigente na turma")
    validar_matricula(db, aluno, turma)
    estado = "lista_de_espera" if turma["estado"] == "lotada" else "confirmada"
    data = instante.isoformat()
    id = db.execute("""
        INSERT INTO matriculas (aluno_id, turma_id, data, estado, confirmada_em) VALUES (?, ?, ?, ?, ?)
    """, (aluno_id, turma_id, data, estado, data if estado == "confirmada" else None)).lastrowid
    atualizar_fila(db, turma_id, instante)
    return obter(db, "matriculas", id)


def confirmar(db, matricula, instante):
    if matricula["estado"] == "confirmada":
        return matricula
    prazo = matricula["oferta_expira_em"]
    if matricula["estado"] != "lista_de_espera" or not prazo or prazo <= instante.isoformat():
        erro(409, "Matrícula sem oferta de vaga vigente")
    validar_matricula(db, obter(db, "alunos", matricula["aluno_id"]),
                      obter(db, "turmas", matricula["turma_id"]))
    db.execute("""
        UPDATE matriculas SET estado = 'confirmada', oferta_expira_em = NULL, confirmada_em = ? WHERE id = ?
    """, (instante.isoformat(), matricula["id"]))
    atualizar_fila(db, matricula["turma_id"], instante)
    return obter(db, "matriculas", matricula["id"])


def cancelar_turma(db, turma_id):
    db.execute("UPDATE turmas SET estado = 'cancelada' WHERE id = ?", (turma_id,))
    db.execute("""
        UPDATE matriculas SET estado = 'cancelada', oferta_expira_em = NULL WHERE turma_id = ?
    """, (turma_id,))


def retirar(db, matricula, instante, *, trancar):
    estado = matricula["estado"]
    destino = "trancada" if trancar else "cancelada"
    if estado == destino:
        return matricula
    if estado not in ("confirmada", "lista_de_espera", "solicitada") or (trancar and estado != "confirmada"):
        erro(409, "Estado da matrícula não permite esta operação")
    aluno = obter(db, "alunos", matricula["aluno_id"])
    turma = obter(db, "turmas", matricula["turma_id"])
    if turma["estado"] in ("encerrada", "cancelada"):
        erro(409, "Turma indisponível")
    _, limite, dias = LIMITES[aluno["categoria"]]
    no_prazo = estado != "confirmada" or instante <= datetime.fromisoformat(
        matricula["confirmada_em"]) + timedelta(days=dias)
    if trancar:
        total = quantidade(db, """
            SELECT count(*) FROM historico WHERE aluno_id = ? AND disciplina_id = ? AND situacao = 'trancado'
        """, (aluno["id"], turma["disciplina_id"]))
        if not no_prazo or total >= limite:
            erro(409, "Prazo ou limite de trancamentos excedido")
    db.execute("UPDATE matriculas SET estado = ?, oferta_expira_em = NULL WHERE id = ?",
               (destino, matricula["id"]))
    if trancar or not no_prazo:
        db.execute("""
            INSERT INTO historico (aluno_id, disciplina_id, semestre, situacao, motivo, matricula_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (aluno["id"], turma["disciplina_id"], turma["semestre"],
              "trancado" if trancar else "reprovado", None if trancar else "falta", matricula["id"]))
    turmas_afetadas = {turma["id"]}
    if trancar and quantidade(db, """
        SELECT count(*) FROM historico WHERE aluno_id = ? AND semestre = ? AND situacao = 'trancado'
    """, (aluno["id"], turma["semestre"])) >= 3:
        db.execute("UPDATE alunos SET situacao = 'trancado' WHERE id = ?", (aluno["id"],))
        for item in db.execute("""
            UPDATE matriculas SET estado = 'cancelada', oferta_expira_em = NULL
            WHERE aluno_id = ? AND estado = 'confirmada' RETURNING turma_id
        """, (aluno["id"],)):
            turmas_afetadas.add(item["turma_id"])
    for turma_id in turmas_afetadas:
        atualizar_fila(db, turma_id, instante)
    return obter(db, "matriculas", matricula["id"])
