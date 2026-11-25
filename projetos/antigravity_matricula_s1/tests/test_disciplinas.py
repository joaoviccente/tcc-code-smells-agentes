import pytest


def test_crud_disciplina(client):
    payload = {
        "codigo": "MAT001",
        "nome": "Cálculo I",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "MATEMATICA"
    }
    r = client.post("/disciplinas", json=payload)
    assert r.status_code == 201
    disc_id = r.json()["id"]
    assert r.json()["codigo"] == "MAT001"
    assert r.json()["numero_creditos"] == 4

    # Duplicate code
    r_dup = client.post("/disciplinas", json=payload)
    assert r_dup.status_code == 409

    # Update
    r_up = client.put(f"/disciplinas/{disc_id}", json={"nome": "Cálculo Diferencial e Integral I"})
    assert r_up.status_code == 200
    assert r_up.json()["nome"] == "Cálculo Diferencial e Integral I"

    # Get
    r_get = client.get(f"/disciplinas/{disc_id}")
    assert r_get.status_code == 200
    assert r_get.json()["id"] == disc_id


def test_prerequisitos(client):
    r1 = client.post("/disciplinas", json={"codigo": "MAT001", "nome": "Cálculo I", "numero_creditos": 4, "carga_horaria": 60, "departamento": "MAT"})
    r2 = client.post("/disciplinas", json={"codigo": "MAT002", "nome": "Cálculo II", "numero_creditos": 4, "carga_horaria": 60, "departamento": "MAT"})
    id_calc1 = r1.json()["id"]
    id_calc2 = r2.json()["id"]

    # Adicionar Cálculo I como pré-requisito de Cálculo II
    r_add = client.post(f"/disciplinas/{id_calc2}/pre-requisitos", json={"prerequisito_id": id_calc1})
    assert r_add.status_code == 201
    assert len(r_add.json()["pre_requisitos"]) == 1
    assert r_add.json()["pre_requisitos"][0]["codigo"] == "MAT001"

    # Tentar adicionar si mesma como pré-requisito (deve falhar)
    r_self = client.post(f"/disciplinas/{id_calc1}/pre-requisitos", json={"prerequisito_id": id_calc1})
    assert r_self.status_code == 400

    # Listar pré-requisitos
    r_list = client.get(f"/disciplinas/{id_calc2}/pre-requisitos")
    assert r_list.status_code == 200
    assert len(r_list.json()) == 1

    # Remover pré-requisito
    r_del = client.delete(f"/disciplinas/{id_calc2}/pre-requisitos/{id_calc1}")
    assert r_del.status_code == 204

    r_list_after = client.get(f"/disciplinas/{id_calc2}/pre-requisitos")
    assert len(r_list_after.json()) == 0
