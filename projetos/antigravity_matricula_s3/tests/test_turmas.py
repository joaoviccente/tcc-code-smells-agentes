def test_criar_e_obter_turma(client):
    d_res = client.post("/disciplinas", json={
        "codigo": "CC101",
        "nome": "Algoritmos",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Ciência da Computação"
    })
    disc_id = d_res.json()["id"]

    turma_payload = {
        "disciplina_id": disc_id,
        "semestre": "2026.1",
        "professor": "Prof. Alan Turing",
        "numero_vagas": 30,
        "horario": "SEG 08:00-10:00, QUA 08:00-10:00",
        "estado": "aberta"
    }
    res = client.post("/turmas", json=turma_payload)
    assert res.status_code == 201
    turma = res.json()
    assert turma["id"] is not None
    assert turma["professor"] == "Prof. Alan Turing"
    assert turma["numero_vagas"] == 30
    assert turma["vagas_disponiveis"] == 30
    assert turma["vagas_ocupadas"] == 0

    # Listar turmas
    list_res = client.get("/turmas?semestre=2026.1")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1
