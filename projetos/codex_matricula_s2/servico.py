from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from banco import atualizar, buscar, inserir, transacao


REGRAS = {
    "graduacao": (28, 2, 15),
    "pos": (16, 1, 30),
    "especial": (8, 0, 7),
}
PRIORIDADE = "CASE a.categoria WHEN 'pos' THEN 0 WHEN 'graduacao' THEN 1 ELSE 2 END"


def agora():
    return datetime.now(timezone.utc).isoformat()


def contar(db, sql, parametros):
    return db.execute(sql, parametros).fetchone()[0]


def validar_matricula(db, aluno, turma):
    if aluno["situacao"] != "ativo":
        raise HTTPException(409, "Aluno precisa estar ativo.")
    aluno_id = aluno["id"]
    disciplina_id = turma["disciplina_id"]
    if contar(db, """
        SELECT COUNT(*) FROM pre_requisitos p WHERE p.disciplina_id = ?
        AND NOT EXISTS (SELECT 1 FROM historico h WHERE h.aluno_id = ?
                        AND h.disciplina_id = p.exigida_id AND h.situacao = 'aprovado')
    """, (disciplina_id, aluno_id)):
        raise HTTPException(409, "Aluno possui pre-requisitos pendentes.")
    if contar(db, """
        SELECT COUNT(*) FROM historico WHERE aluno_id = ? AND disciplina_id = ?
        AND situacao = 'reprovado'
    """, (aluno_id, disciplina_id)) >= 3:
        raise HTTPException(409, "Aluno atingiu tres reprovacoes na disciplina.")
    creditos = contar(db, """
        SELECT COALESCE(SUM(d.creditos), 0)
        FROM matriculas m JOIN turmas t ON t.id = m.turma_id
        JOIN disciplinas d ON d.id = t.disciplina_id
        WHERE m.aluno_id = ? AND m.estado = 'confirmada' AND t.semestre = ?
    """, (aluno_id, turma["semestre"]))
    if creditos + buscar(db, "disciplinas", disciplina_id)["creditos"] > REGRAS[aluno["categoria"]][0]:
        raise HTTPException(409, "Limite de creditos do semestre excedido.")
    if contar(db, """
        SELECT COUNT(*) FROM matriculas m JOIN turmas t ON t.id = m.turma_id
        WHERE m.aluno_id = ? AND m.estado = 'confirmada' AND t.semestre = ?
        AND t.dia_semana = ? AND t.inicio < ? AND t.fim > ?
    """, (aluno_id, turma["semestre"], turma["dia_semana"], turma["fim"], turma["inicio"])):
        raise HTTPException(409, "Horario conflita com uma turma confirmada.")


def fila(db, turma_id):
    return db.execute(f"""
        SELECT m.*, a.categoria FROM matriculas m JOIN alunos a ON a.id = m.aluno_id
        WHERE m.turma_id = ? AND m.estado = 'lista_de_espera'
        ORDER BY {PRIORIDADE}, m.data, m.id
    """, (turma_id,)).fetchall()


def ocupadas(db, turma_id):
    return contar(db, """
        SELECT COUNT(*) FROM matriculas WHERE turma_id = ?
        AND estado IN ('confirmada', 'solicitada')
    """, (turma_id,))


def distribuir_vagas(db, turma_id, instante):
    turma = buscar(db, "turmas", turma_id)
    if turma["estado"] in ("cancelada", "encerrada"):
        return
    livres = turma["vagas"] - ocupadas(db, turma_id)
    if livres > 0:
        for pedido in fila(db, turma_id):
            aluno = buscar(db, "alunos", pedido["aluno_id"])
            try:
                validar_matricula(db, aluno, turma)
            except HTTPException as erro:
                if erro.status_code != 409:
                    raise
                atualizar(db, "matriculas", pedido["id"], {"estado": "cancelada"})
                continue
            prazo = datetime.fromisoformat(instante) + timedelta(hours=48)
            atualizar(db, "matriculas", pedido["id"],
                      {"estado": "solicitada", "prazo_confirmacao": prazo.isoformat()})
            livres -= 1
            if livres == 0:
                break
    atualizar(db, "turmas", turma_id, {"estado": "lotada" if livres <= 0 else "aberta"})


def expirar_ofertas():
    with transacao() as db:
        instante = agora()
        expiradas = db.execute("""
            UPDATE matriculas SET estado = 'cancelada', prazo_confirmacao = NULL
            WHERE estado = 'solicitada' AND prazo_confirmacao <= ?
            RETURNING turma_id
        """, (instante,)).fetchall()
        for turma_id in sorted({item["turma_id"] for item in expiradas}):
            distribuir_vagas(db, turma_id, instante)


def solicitar(db, dados):
    aluno = buscar(db, "alunos", dados.aluno_id)
    turma = buscar(db, "turmas", dados.turma_id)
    if turma["periodo_encerrado"] or turma["estado"] in ("cancelada", "encerrada"):
        raise HTTPException(409, "Turma fora do periodo de matricula.")
    validar_matricula(db, aluno, turma)
    instante = agora()
    estado = "solicitada" if ocupadas(db, turma["id"]) < turma["vagas"] else "lista_de_espera"
    id = inserir(db, "matriculas", {**dados.model_dump(), "data": instante, "estado": estado})
    distribuir_vagas(db, turma["id"], instante)
    return buscar(db, "matriculas", id)


def confirmar(db, id):
    pedido = buscar(db, "matriculas", id)
    turma = buscar(db, "turmas", pedido["turma_id"])
    instante = agora()
    if pedido["estado"] != "solicitada" or turma["estado"] in ("cancelada", "encerrada"):
        raise HTTPException(409, "Matricula sem reserva disponivel para confirmacao.")
    if pedido["prazo_confirmacao"] and pedido["prazo_confirmacao"] <= instante:
        raise HTTPException(409, "Prazo de confirmacao expirado.")
    validar_matricula(db, buscar(db, "alunos", pedido["aluno_id"]), turma)
    atualizar(db, "matriculas", id, {
        "estado": "confirmada", "confirmada_em": instante, "prazo_confirmacao": None,
    })
    return buscar(db, "matriculas", id)


def desfazer(db, id, trancar=False):
    pedido = buscar(db, "matriculas", id)
    turma = buscar(db, "turmas", pedido["turma_id"])
    aluno = buscar(db, "alunos", pedido["aluno_id"])
    if turma["estado"] in ("cancelada", "encerrada"):
        raise HTTPException(409, "Turma cancelada ou encerrada.")
    if pedido["estado"] not in ("confirmada", "solicitada", "lista_de_espera"):
        raise HTTPException(409, "Matricula ja cancelada ou trancada.")
    if trancar and pedido["estado"] != "confirmada":
        raise HTTPException(409, "O trancamento exige matricula confirmada.")

    instante = agora()
    limite = REGRAS[aluno["categoria"]]
    fora_do_prazo = pedido["confirmada_em"] is not None and (
        datetime.fromisoformat(instante)
        > datetime.fromisoformat(pedido["confirmada_em"]) + timedelta(days=limite[2])
    )
    disciplina_id = turma["disciplina_id"]
    if trancar:
        total = contar(db, """
            SELECT COUNT(*) FROM historico WHERE aluno_id = ? AND disciplina_id = ?
            AND situacao = 'trancado'
        """, (aluno["id"], disciplina_id))
        if fora_do_prazo or total >= limite[1]:
            raise HTTPException(409, "Prazo ou limite de trancamentos excedido.")
    atualizar(db, "matriculas", id, {
        "estado": "trancada" if trancar else "cancelada", "prazo_confirmacao": None,
    })
    if trancar or fora_do_prazo:
        inserir(db, "historico", {
            "aluno_id": aluno["id"], "disciplina_id": disciplina_id, "semestre": turma["semestre"],
            "situacao": "trancado" if trancar else "reprovado",
            "motivo": None if trancar else "falta", "matricula_id": id,
        })
    turmas = {turma["id"]}
    if trancar:
        turmas.update(aplicar_trancamento_do_aluno(db, aluno["id"], turma["semestre"]))
    for turma_id in sorted(turmas):
        distribuir_vagas(db, turma_id, instante)
    return buscar(db, "matriculas", id)


def aplicar_trancamento_do_aluno(db, aluno_id, semestre):
    total = contar(db, """
        SELECT COUNT(*) FROM historico WHERE aluno_id = ? AND semestre = ?
        AND situacao = 'trancado'
    """, (aluno_id, semestre))
    if total < 3:
        return set()
    atualizar(db, "alunos", aluno_id, {"situacao": "trancado"})
    canceladas = db.execute("""
        UPDATE matriculas SET estado = 'cancelada', prazo_confirmacao = NULL
        WHERE aluno_id = ? AND estado IN ('confirmada', 'solicitada', 'lista_de_espera')
        RETURNING turma_id
    """, (aluno_id,)).fetchall()
    return {item["turma_id"] for item in canceladas}


def cancelar_turma(db, id):
    atualizar(db, "turmas", id, {"estado": "cancelada", "periodo_encerrado": 1})
    db.execute("""
        UPDATE matriculas SET estado = 'cancelada', prazo_confirmacao = NULL WHERE turma_id = ?
    """, (id,))


def fechar_periodo(db, id):
    turma = buscar(db, "turmas", id)
    if turma["periodo_encerrado"]:
        return
    if contar(db, "SELECT COUNT(*) FROM matriculas WHERE turma_id = ? AND estado = 'confirmada'",
              (id,)) < 5:
        cancelar_turma(db, id)
    else:
        atualizar(db, "turmas", id, {"periodo_encerrado": 1})
