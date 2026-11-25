def test_criar_disciplina_com_prerequisito(client):
    # Criar disciplina base
    res_calc1 = client.post("/disciplinas", json={
        "codigo": "MAT101",
        "nome": "Cálculo I",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matemática"
    })
    assert res_calc1.status_code == 201
    calc1_id = res_calc1.json()["id"]

    # Criar disciplina dependente com pré-requisito
    res_calc2 = client.post("/disciplinas", json={
        "codigo": "MAT102",
        "nome": "Cálculo II",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matemática",
        "prerequisitos_ids": [calc1_id]
    })
    assert res_calc2.status_code == 201
    data_calc2 = res_calc2.json()
    assert len(data_calc2["prerequisitos"]) == 1
    assert data_calc2["prerequisitos"][0]["codigo"] == "MAT101"


def test_impedir_auto_prerequisito(client):
    res = client.post("/disciplinas", json={
        "codigo": "FIS101",
        "nome": "Física I",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Física"
    })
    disc_id = res.json()["id"]

    res_auto = client.post(f"/disciplinas/{disc_id}/prerequisitos/{disc_id}")
    assert res_auto.status_code == 400


def test_gerenciar_prerequisitos_via_endpoints(client):
    res_a = client.post("/disciplinas", json={
        "codigo": "ALG1",
        "nome": "Álgebra Linear",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matemática"
    })
    res_b = client.post("/disciplinas", json={
        "codigo": "GEO1",
        "nome": "Geometria Analítica",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matemática"
    })
    id_a = res_a.json()["id"]
    id_b = res_b.json()["id"]

    # Adicionar pré-requisito
    res_add = client.post(f"/disciplinas/{id_a}/prerequisitos/{id_b}")
    assert res_add.status_code == 201

    # Verificar adição
    res_get = client.get(f"/disciplinas/{id_a}")
    assert len(res_get.json()["prerequisitos"]) == 1

    # Remover pré-requisito
    res_del = client.delete(f"/disciplinas/{id_a}/prerequisitos/{id_b}")
    assert res_del.status_code == 204

    # Verificar remoção
    res_get2 = client.get(f"/disciplinas/{id_a}")
    assert len(res_get2.json()["prerequisitos"]) == 0
