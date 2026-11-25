from datetime import datetime, timedelta, timezone
import pytest


def test_conflito_horario_adjacente_nao_conflita(client):
    """
    Horários contíguos (ex: 08:00-10:00 e 10:00-12:00) NÃO devem conflitar.
    """
    d1 = client.post("/disciplinas", json={
        "codigo": "ADJ1",
        "nome": "Disciplina Adjacente 1",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Geral"
    }).json()

    d2 = client.post("/disciplinas", json={
        "codigo": "ADJ2",
        "nome": "Disciplina Adjacente 2",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Geral"
    }).json()

    t1 = client.post("/turmas", json={
        "disciplina_id": d1["id"],
        "semestre": "2026.1",
        "professor": "Prof 1",
        "numero_vagas": 20,
        "horario": "SEG 08:00-10:00"
    }).json()

    t2 = client.post("/turmas", json={
        "disciplina_id": d2["id"],
        "semestre": "2026.1",
        "professor": "Prof 2",
        "numero_vagas": 20,
        "horario": "SEG 10:00-12:00"
    }).json()

    aluno = client.post("/alunos", json={
        "nome": "Aluno Adjacente",
        "matricula": "ADJ001",
        "email": "adj@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    res1 = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": t1["id"]})
    assert res1.status_code == 201

    res2 = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": t2["id"]})
    assert res2.status_code == 201


def test_matricula_duplicada_na_mesma_disciplina_rejeitada(client):
    """
    Tentar se matricular em duas turmas diferentes da mesma disciplina no mesmo semestre deve retornar 409 Conflict.
    """
    d = client.post("/disciplinas", json={
        "codigo": "DUP1",
        "nome": "Disciplina Duplicada",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Geral"
    }).json()

    t1 = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Prof Manha",
        "numero_vagas": 20,
        "horario": "SEG 08:00-10:00"
    }).json()

    t2 = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Prof Noite",
        "numero_vagas": 20,
        "horario": "TER 19:00-21:00"
    }).json()

    aluno = client.post("/alunos", json={
        "nome": "Aluno Dup",
        "matricula": "DUP001",
        "email": "dup@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    res1 = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": t1["id"]})
    assert res1.status_code == 201

    # Segunda turma da mesma disciplina no mesmo semestre
    res2 = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": t2["id"]})
    assert res2.status_code == 409
    assert "matrícula ativa" in res2.json()["detail"].lower()


def test_limite_trancamentos_por_disciplina(client):
    """
    Graduação: até 2 trancamentos por disciplina
    Pós: 1 trancamento por disciplina
    """
    # Aluno Pós: max 1 trancamento
    aluno_pos = client.post("/alunos", json={
        "nome": "Aluno Pos Trancamento",
        "matricula": "POSTR01",
        "email": "postr@univ.br",
        "categoria": "pos",
        "situacao": "ativo"
    }).json()

    d = client.post("/disciplinas", json={
        "codigo": "POSTR_D",
        "nome": "Topicos Avancados",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Computacao"
    }).json()

    # Já tem 1 trancamento registrado no histórico para esta disciplina
    client.post(f"/alunos/{aluno_pos['id']}/historico", json={
        "aluno_id": aluno_pos["id"],
        "disciplina_id": d["id"],
        "semestre": "2025.1",
        "situacao": "trancado"
    })

    t = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Prof Pós",
        "numero_vagas": 10,
        "horario": "QUI 14:00-16:00"
    }).json()

    # Pode matricular novamente
    mat = client.post("/matriculas", json={"aluno_id": aluno_pos["id"], "turma_id": t["id"]}).json()
    assert mat["estado"] == "confirmada"

    # Tenta trancar pela 2ª vez nesta disciplina -> Bloqueado (limite de 1 para Pós)
    res_tranc = client.post(f"/matriculas/{mat['id']}/trancar")
    assert res_tranc.status_code == 400
    assert "limite de trancamentos" in res_tranc.json()["detail"].lower()


def test_dependencia_circular_cadeia_longa(client):
    """
    A -> B -> C -> A deve ser rejeitada como dependência circular.
    """
    da = client.post("/disciplinas", json={
        "codigo": "DISC_A", "nome": "Disciplina A", "numero_creditos": 4, "carga_horaria": 60, "departamento": "Depto A"
    }).json()
    db = client.post("/disciplinas", json={
        "codigo": "DISC_B", "nome": "Disciplina B", "numero_creditos": 4, "carga_horaria": 60, "departamento": "Depto B"
    }).json()
    dc = client.post("/disciplinas", json={
        "codigo": "DISC_C", "nome": "Disciplina C", "numero_creditos": 4, "carga_horaria": 60, "departamento": "Depto C"
    }).json()

    # B exige A
    res_ba = client.post(f"/disciplinas/{db['id']}/pre-requisitos", json={"pre_requisito_id": da["id"]})
    assert res_ba.status_code == 201

    # C exige B
    res_cb = client.post(f"/disciplinas/{dc['id']}/pre-requisitos", json={"pre_requisito_id": db["id"]})
    assert res_cb.status_code == 201

    # Tentar fazer A exigir C (criaria o ciclo A -> C -> B -> A)
    res_ac = client.post(f"/disciplinas/{da['id']}/pre-requisitos", json={"pre_requisito_id": dc["id"]})
    assert res_ac.status_code == 400
    assert "circular" in res_ac.json()["detail"].lower()


def test_cancelar_aluno_em_lista_de_espera(client):
    """
    Aluno que está em lista de espera cancela sua solicitação.
    """
    d = client.post("/disciplinas", json={
        "codigo": "FILA_CANC", "nome": "Fila Cancela", "numero_creditos": 4, "carga_horaria": 60, "departamento": "Depto Fila"
    }).json()

    t = client.post("/turmas", json={
        "disciplina_id": d["id"], "semestre": "2026.1", "professor": "Prof Fila", "numero_vagas": 1, "horario": "SEX 14:00-16:00"
    }).json()

    a1 = client.post("/alunos", json={
        "nome": "Aluno F1", "matricula": "F01", "email": "f1@univ.br", "categoria": "graduacao", "situacao": "ativo"
    }).json()
    a2 = client.post("/alunos", json={
        "nome": "Aluno F2", "matricula": "F02", "email": "f2@univ.br", "categoria": "graduacao", "situacao": "ativo"
    }).json()

    # a1 ocupa a vaga
    client.post("/matriculas", json={"aluno_id": a1["id"], "turma_id": t["id"]})
    # a2 vai para a fila
    mat2 = client.post("/matriculas", json={"aluno_id": a2["id"], "turma_id": t["id"]}).json()
    assert mat2["estado"] == "lista_de_espera"

    # a2 cancela enquanto na fila
    res_canc = client.post(f"/matriculas/{mat2['id']}/cancelar")
    assert res_canc.status_code == 200
    assert res_canc.json()["estado"] == "cancelada"

    # Fila deve estar vazia
    fila = client.get(f"/turmas/{t['id']}/fila").json()
    assert fila["total_na_fila"] == 0
