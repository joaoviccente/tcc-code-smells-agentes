def test_criar_aluno_sucesso(client):
    payload = {
        "nome": "Carlos Silva",
        "matricula": "2026001",
        "e_mail": "carlos@universidade.edu.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }
    response = client.post("/alunos", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "Carlos Silva"
    assert data["matricula"] == "2026001"
    assert data["categoria"] == "graduacao"
    assert data["situacao"] == "ativo"


def test_duplicidade_matricula_ou_email(client):
    payload1 = {
        "nome": "Carlos Silva",
        "matricula": "2026001",
        "e_mail": "carlos@universidade.edu.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }
    res1 = client.post("/alunos", json=payload1)
    assert res1.status_code == 201

    # Mesma matrícula
    payload2 = {
        "nome": "Carlos Outro",
        "matricula": "2026001",
        "e_mail": "outro@universidade.edu.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }
    res2 = client.post("/alunos", json=payload2)
    assert res2.status_code == 409

    # Mesmo email
    payload3 = {
        "nome": "Carlos Outro",
        "matricula": "2026002",
        "e_mail": "carlos@universidade.edu.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }
    res3 = client.post("/alunos", json=payload3)
    assert res3.status_code == 409


def test_listar_e_filtrar_alunos(client):
    client.post("/alunos", json={
        "nome": "Aluno Grad", "matricula": "G01", "e_mail": "g01@test.com", "categoria": "graduacao"
    })
    client.post("/alunos", json={
        "nome": "Aluno Pos", "matricula": "P01", "e_mail": "p01@test.com", "categoria": "pos"
    })
    client.post("/alunos", json={
        "nome": "Aluno Esp", "matricula": "E01", "e_mail": "e01@test.com", "categoria": "especial", "situacao": "trancado"
    })

    # Filtro por categoria
    res_pos = client.get("/alunos?categoria=pos")
    assert res_pos.status_code == 200
    assert len(res_pos.json()) == 1
    assert res_pos.json()[0]["matricula"] == "P01"

    # Filtro por situacao
    res_tranc = client.get("/alunos?situacao=trancado")
    assert res_tranc.status_code == 200
    assert len(res_tranc.json()) == 1
    assert res_tranc.json()[0]["matricula"] == "E01"


def test_atualizar_e_deletar_aluno(client):
    res = client.post("/alunos", json={
        "nome": "Teste Update", "matricula": "U01", "e_mail": "u01@test.com", "categoria": "graduacao"
    })
    aluno_id = res.json()["id"]

    # Update
    res_up = client.put(f"/alunos/{aluno_id}", json={"nome": "Nome Atualizado", "situacao": "trancado"})
    assert res_up.status_code == 200
    assert res_up.json()["nome"] == "Nome Atualizado"
    assert res_up.json()["situacao"] == "trancado"

    # Delete
    res_del = client.delete(f"/alunos/{aluno_id}")
    assert res_del.status_code == 204

    # Buscar deletado -> 404
    res_get = client.get(f"/alunos/{aluno_id}")
    assert res_get.status_code == 404
