def test_criar_e_obter_disciplina_com_prerequisitos(client):
    # Criar Cálculo 1
    res1 = client.post("/disciplinas", json={
        "codigo": "MAT101",
        "nome": "Cálculo 1",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matemática"
    })
    assert res1.status_code == 201
    disc1 = res1.json()

    # Criar Cálculo 2 com pré-requisito Cálculo 1
    res2 = client.post("/disciplinas", json={
        "codigo": "MAT102",
        "nome": "Cálculo 2",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matemática",
        "pre_requisito_ids": [disc1["id"]]
    })
    assert res2.status_code == 201
    disc2 = res2.json()
    assert len(disc2["pre_requisitos"]) == 1
    assert disc2["pre_requisitos"][0]["codigo"] == "MAT101"

    # Não permitir pré-requisito de si mesma
    res_self = client.put(f"/disciplinas/{disc1['id']}", json={
        "pre_requisito_ids": [disc1["id"]]
    })
    assert res_self.status_code == 400

def test_adicionar_e_remover_pre_requisito_endpoint(client):
    res_a = client.post("/disciplinas", json={
        "codigo": "FIS101",
        "nome": "Física 1",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Física"
    })
    id_a = res_a.json()["id"]

    res_b = client.post("/disciplinas", json={
        "codigo": "FIS102",
        "nome": "Física 2",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Física"
    })
    id_b = res_b.json()["id"]

    # Adicionar pré-requisito
    add_res = client.post(f"/disciplinas/{id_b}/pre-requisitos/{id_a}")
    assert add_res.status_code == 200
    assert len(add_res.json()["pre_requisitos"]) == 1

    # Remover pré-requisito
    rem_res = client.delete(f"/disciplinas/{id_b}/pre-requisitos/{id_a}")
    assert rem_res.status_code == 200
    assert len(rem_res.json()["pre_requisitos"]) == 0
