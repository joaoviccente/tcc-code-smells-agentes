import pytest


def test_criar_disciplina_sucesso(client):
    response = client.post("/disciplinas", json={
        "codigo": "MAT101",
        "nome": "Calculo 1",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matematica"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["codigo"] == "MAT101"
    assert data["numero_creditos"] == 4
    assert data["pre_requisitos"] == []


def test_criar_disciplina_codigo_duplicado(client):
    client.post("/disciplinas", json={
        "codigo": "MAT101",
        "nome": "Calculo 1",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matematica"
    })
    response = client.post("/disciplinas", json={
        "codigo": "MAT101",
        "nome": "Outro Calculo",
        "numero_creditos": 6,
        "carga_horaria": 90,
        "departamento": "Matematica"
    })
    assert response.status_code == 409


def test_pre_requisito_fluxo_completo(client):
    # Criar MAT101 e MAT102
    d1 = client.post("/disciplinas", json={
        "codigo": "MAT101",
        "nome": "Calculo 1",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matematica"
    }).json()

    d2 = client.post("/disciplinas", json={
        "codigo": "MAT102",
        "nome": "Calculo 2",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matematica"
    }).json()

    # Adicionar MAT101 como pré-requisito de MAT102
    res_prereq = client.post(f"/disciplinas/{d2['id']}/pre-requisitos", json={
        "pre_requisito_id": d1["id"]
    })
    assert res_prereq.status_code == 201
    assert res_prereq.json()["codigo"] == "MAT101"

    # Consultar disciplina e ver o pré-requisito
    get_d2 = client.get(f"/disciplinas/{d2['id']}")
    assert len(get_d2.json()["pre_requisitos"]) == 1
    assert get_d2.json()["pre_requisitos"][0]["codigo"] == "MAT101"

    # Tentar adicionar a si mesma como pré-requisito -> 400
    res_self = client.post(f"/disciplinas/{d1['id']}/pre-requisitos", json={
        "pre_requisito_id": d1["id"]
    })
    assert res_self.status_code == 400

    # Tentar dependência circular: adicionar MAT102 como pré-requisito de MAT101 -> 400
    res_circ = client.post(f"/disciplinas/{d1['id']}/pre-requisitos", json={
        "pre_requisito_id": d2["id"]
    })
    assert res_circ.status_code == 400

    # Remover pré-requisito
    del_prereq = client.delete(f"/disciplinas/{d2['id']}/pre-requisitos/{d1['id']}")
    assert del_prereq.status_code == 204

    get_d2_after = client.get(f"/disciplinas/{d2['id']}")
    assert len(get_d2_after.json()["pre_requisitos"]) == 0
