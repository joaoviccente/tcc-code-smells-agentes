import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

# Limite de créditos, limite de trancamentos e prazo em dias.
REGRAS = {"graduacao": (28, 2, 15), "pos": (16, 1, 30), "especial": (8, 0, 7)}
ORDEM_FILA = """
    CASE a.categoria WHEN 'pos' THEN 1 WHEN 'graduacao' THEN 2 ELSE 3 END,
    m.data, m.id
"""


def agora():
    return datetime.now(timezone.utc)


def obter(db, tabela, identificador):
    item = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (identificador,)).fetchone()
    if item is None:
        raise HTTPException(404, "Registro não encontrado.")
    return dict(item)


def exigir(condicao, detalhe):
    if not condicao:
        raise HTTPException(409, detalhe)


def fila(db, turma_id):
    return [dict(item) for item in db.execute(f"""
        SELECT m.*, a.categoria
        FROM matriculas m JOIN alunos a ON a.id = m.aluno_id
        WHERE m.turma_id = ? AND m.estado = 'lista_de_espera'
        ORDER BY CASE WHEN m.prazo_confirmacao IS NULL THEN 1 ELSE 0 END,
                 m.prazo_confirmacao, {ORDEM_FILA}
    """, (turma_id,))]


def ocupadas(db, turma_id):
    return db.execute("""
        SELECT COUNT(*) FROM matriculas WHERE turma_id = ?
        AND (estado = 'confirmada' OR (estado = 'lista_de_espera' AND prazo_confirmacao IS NOT NULL))
    """, (turma_id,)).fetchone()[0]


def atualizar_fila(db, turma_id, instante):
    turma = obter(db, "turmas", turma_id)
    if turma["estado"] not in ("aberta", "lotada"):
        return
    db.execute("""
        UPDATE matriculas SET estado = 'cancelada', prazo_confirmacao = NULL
        WHERE turma_id = ? AND estado = 'lista_de_espera' AND prazo_confirmacao <= ?
    """, (turma_id, instante.isoformat()))
    vagas = turma["vagas"] - ocupadas(db, turma_id)
    if vagas > 0:
        prazo = (instante + timedelta(hours=48)).isoformat()
        for item in fila(db, turma_id):
            if item["prazo_confirmacao"] is not None:
                continue
            db.execute("UPDATE matriculas SET prazo_confirmacao = ? WHERE id = ?", (prazo, item["id"]))
            vagas -= 1
            if vagas == 0:
                break
    estado = "aberta" if vagas > 0 else "lotada"
    db.execute("UPDATE turmas SET estado = ? WHERE id = ? AND estado <> ?", (estado, turma_id, estado))


def expirar_ofertas(db, instante):
    turmas = db.execute("""
        SELECT DISTINCT turma_id FROM matriculas
        WHERE estado = 'lista_de_espera' AND prazo_confirmacao <= ?
    """, (instante.isoformat(),)).fetchall()
    for turma in turmas:
        atualizar_fila(db, turma["turma_id"], instante)


def validar_matricula(db, aluno, turma):
    exigir(aluno["situacao"] == "ativo", "Aluno precisa estar ativo.")
    exigir(turma["estado"] in ("aberta", "lotada"), "Turma indisponível para matrícula.")
    aluno_id, disciplina_id = aluno["id"], turma["disciplina_id"]
    faltante = db.execute("""
        SELECT 1 FROM pre_requisitos p WHERE p.disciplina_id = ? AND NOT EXISTS (
            SELECT 1 FROM historico h
            WHERE h.aluno_id = ? AND h.disciplina_id = p.exigida_id AND h.situacao = 'aprovado'
        )
    """, (disciplina_id, aluno_id)).fetchone()
    exigir(not faltante, "Pré-requisito pendente.")
    reprovacoes = db.execute("""
        SELECT COUNT(*) FROM historico
        WHERE aluno_id = ? AND disciplina_id = ? AND situacao = 'reprovado'
    """, (aluno_id, disciplina_id)).fetchone()[0]
    exigir(reprovacoes < 3, "Aluno tem três ou mais reprovações na disciplina.")
    confirmadas = db.execute("""
        SELECT t.horario, d.creditos FROM matriculas m
        JOIN turmas t ON t.id = m.turma_id JOIN disciplinas d ON d.id = t.disciplina_id
        WHERE m.aluno_id = ? AND m.estado = 'confirmada' AND t.semestre = ?
    """, (aluno_id, turma["semestre"])).fetchall()
    creditos = obter(db, "disciplinas", disciplina_id)["creditos"]
    exigir(creditos + sum(item["creditos"] for item in confirmadas) <= REGRAS[aluno["categoria"]][0],
           "Limite de créditos do semestre excedido.")
    horarios = json.loads(turma["horario"])
    for item in confirmadas:
        conflito = any(a["dia"] == b["dia"] and a["inicio"] < b["fim"] and b["inicio"] < a["fim"]
                       for a in horarios for b in json.loads(item["horario"]))
        exigir(not conflito, "Conflito de horário com matrícula confirmada.")


def solicitar(db, aluno_id, turma_id, instante):
    aluno = obter(db, "alunos", aluno_id)
    turma = obter(db, "turmas", turma_id)
    exigir(not db.execute("SELECT 1 FROM periodos_encerrados WHERE semestre = ?",
                          (turma["semestre"],)).fetchone(), "Período de matrícula encerrado.")
    exigir(not db.execute("""
        SELECT 1 FROM matriculas WHERE aluno_id = ? AND turma_id = ?
        AND estado IN ('solicitada', 'confirmada', 'lista_de_espera')
    """, (aluno_id, turma_id)).fetchone(), "Já existe matrícula vigente na turma.")
    validar_matricula(db, aluno, turma)
    estado = "confirmada" if ocupadas(db, turma_id) < turma["vagas"] else "lista_de_espera"
    data = instante.isoformat()
    confirmada_em = data if estado == "confirmada" else None
    registro = db.execute("""
        INSERT INTO matriculas (aluno_id, turma_id, data, estado, confirmada_em)
        VALUES (?, ?, ?, ?, ?)
    """, (aluno_id, turma_id, data, estado, confirmada_em)).lastrowid
    atualizar_fila(db, turma_id, instante)
    return obter(db, "matriculas", registro)


def confirmar(db, identificador, instante):
    item = obter(db, "matriculas", identificador)
    if item["estado"] == "confirmada":
        return item
    exigir(item["estado"] == "lista_de_espera" and item["prazo_confirmacao"]
           and instante.isoformat() < item["prazo_confirmacao"], "Não há oferta vigente para esta matrícula.")
    turma = obter(db, "turmas", item["turma_id"])
    validar_matricula(db, obter(db, "alunos", item["aluno_id"]), turma)
    db.execute("""
        UPDATE matriculas SET estado = 'confirmada', confirmada_em = ?, prazo_confirmacao = NULL
        WHERE id = ?
    """, (instante.isoformat(), identificador))
    atualizar_fila(db, turma["id"], instante)
    return obter(db, "matriculas", identificador)


def cancelar_turma(db, turma_id, estado="cancelada"):
    db.execute("UPDATE turmas SET estado = ? WHERE id = ?", (estado, turma_id))
    if estado == "cancelada":
        db.execute("""
            UPDATE matriculas SET estado = 'cancelada', prazo_confirmacao = NULL WHERE turma_id = ?
        """, (turma_id,))
    else:
        db.execute("""
            UPDATE matriculas SET estado = 'cancelada', prazo_confirmacao = NULL
            WHERE turma_id = ? AND estado IN ('solicitada', 'lista_de_espera')
        """, (turma_id,))


def alterar_matricula(db, identificador, trancar, instante):
    item = obter(db, "matriculas", identificador)
    destino = "trancada" if trancar else "cancelada"
    if item["estado"] == destino:
        return item
    estados = ("confirmada",) if trancar else ("confirmada", "lista_de_espera", "solicitada")
    exigir(item["estado"] in estados, "Transição de matrícula não permitida.")
    turma = obter(db, "turmas", item["turma_id"])
    exigir(turma["estado"] in ("aberta", "lotada"), "Turma indisponível para alteração.")
    aluno = obter(db, "alunos", item["aluno_id"])
    aluno_id, disciplina_id = aluno["id"], turma["disciplina_id"]
    _, limite, dias = REGRAS[aluno["categoria"]]
    semestre = turma["semestre"]
    tardio = item["estado"] == "confirmada" and instante > (
        datetime.fromisoformat(item["confirmada_em"]) + timedelta(days=dias)
    )
    if trancar:
        exigir(not tardio, "Prazo de trancamento encerrado.")
        total = db.execute("""
            SELECT COUNT(*) FROM historico WHERE aluno_id = ? AND disciplina_id = ? AND situacao = 'trancado'
        """, (aluno_id, disciplina_id)).fetchone()[0]
        exigir(total < limite, "Limite de trancamentos na disciplina atingido.")
    db.execute("""
        UPDATE matriculas SET estado = ?, prazo_confirmacao = NULL WHERE id = ?
    """, (destino, identificador))
    if trancar or tardio:
        db.execute("""
            INSERT INTO historico (aluno_id, disciplina_id, semestre, situacao, motivo, matricula_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (aluno_id, disciplina_id, semestre, "trancado" if trancar else "reprovado",
              None if trancar else "falta", identificador))
    turmas_liberadas = {turma["id"]}
    if trancar:
        total_semestre = db.execute("""
            SELECT COUNT(*) FROM historico WHERE aluno_id = ? AND semestre = ? AND situacao = 'trancado'
        """, (aluno_id, semestre)).fetchone()[0]
        if total_semestre >= 3:
            db.execute("UPDATE alunos SET situacao = 'trancado' WHERE id = ?", (aluno_id,))
            outras = db.execute("""
                UPDATE matriculas SET estado = 'cancelada' WHERE aluno_id = ? AND estado = 'confirmada'
                RETURNING turma_id
            """, (aluno_id,)).fetchall()
            turmas_liberadas.update(item["turma_id"] for item in outras)
    for turma_id in turmas_liberadas:
        atualizar_fila(db, turma_id, instante)
    return obter(db, "matriculas", identificador)

