def test_criar_turma_horario_valido(client):
    res_disc = client.post("/disciplinas", json={
        "codigo": "INF101",
        "nome": "Introdução à Programação",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Informática"
    })
    disc_id = res_disc.json()["id"]

    res_turma = client.post("/turmas", json={
        "disciplina_id": disc_id,
        "semestre": "2026.1",
        "professor": "Dr. Alan Turing",
        "numero_vagas": 30,
        "horario": "SEG 08:00-10:00, QUA 08:00-10:00"
    })
    assert res_turma.status_code == 201
    data = res_turma.json()
    assert data["professor"] == "Dr. Alan Turing"
    assert data["vagas_ocupadas"] == 0
    assert data["vagas_restantes"] == 30
    assert data["estado"] == "aberta"


def test_criar_turma_horario_invalido(client):
    res_disc = client.post("/disciplinas", json={
        "codigo": "INF102",
        "nome": "Estruturas de Dados",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Informática"
    })
    disc_id = res_disc.json()["id"]

    res_turma = client.post("/turmas", json={
        "disciplina_id": disc_id,
        "semestre": "2026.1",
        "professor": "Dra. Ada Lovelace",
        "numero_vagas": 20,
        "horario": "HORARIO_INVALIDO"
    })
    assert res_turma.status_code == 400
