def test_criar_e_obter_aluno(client):
    payload = {
        "nome": "Carlos Silva",
        "matricula": "202601",
        "email": "carlos@universidade.edu.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }
    response = client.post("/alunos", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "Carlos Silva"
    assert data["matricula"] == "202601"
    assert data["categoria"] == "graduacao"
    assert data["situacao"] == "ativo"

    # Get aluno by id
    get_res = client.get(f"/alunos/{data['id']}")
    assert get_res.status_code == 200
    assert get_res.json()["email"] == "carlos@universidade.edu.br"

def test_duplicidade_matricula_e_email(client):
    payload = {
        "nome": "Carlos Silva",
        "matricula": "202601",
        "email": "carlos@universidade.edu.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }
    client.post("/alunos", json=payload)

    # Duplicate matricula
    res_dup_mat = client.post("/alunos", json={
        "nome": "Outro Aluno",
        "matricula": "202601",
        "email": "outro@universidade.edu.br",
        "categoria": "graduacao"
    })
    assert res_dup_mat.status_code == 409

    # Duplicate email
    res_dup_email = client.post("/alunos", json={
        "nome": "Outro Aluno",
        "matricula": "202602",
        "email": "carlos@universidade.edu.br",
        "categoria": "graduacao"
    })
    assert res_dup_email.status_code == 409

def test_atualizar_e_deletar_aluno(client):
    res = client.post("/alunos", json={
        "nome": "Maria Santos",
        "matricula": "202603",
        "email": "maria@universidade.edu.br",
        "categoria": "pos",
        "situacao": "ativo"
    })
    aluno_id = res.json()["id"]

    # Update
    update_res = client.put(f"/alunos/{aluno_id}", json={"situacao": "trancado"})
    assert update_res.status_code == 200
    assert update_res.json()["situacao"] == "trancado"

    # Delete
    del_res = client.delete(f"/alunos/{aluno_id}")
    assert del_res.status_code == 204

    # Verify not found
    get_res = client.get(f"/alunos/{aluno_id}")
    assert get_res.status_code == 404
