def test_criar_usuario(client):
    response = client.post("/usuarios", json={
        "nome": "João Silva",
        "email": "joao@universidade.edu.br",
        "matricula": "20260001",
        "categoria": "aluno"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "João Silva"
    assert data["email"] == "joao@universidade.edu.br"
    assert data["matricula"] == "20260001"
    assert data["categoria"] == "aluno"
    assert data["situacao"] == "ativo"

def test_duplicidade_usuario(client):
    payload = {
        "nome": "Maria Souza",
        "email": "maria@universidade.edu.br",
        "matricula": "20260002",
        "categoria": "professor"
    }
    res1 = client.post("/usuarios", json=payload)
    assert res1.status_code == 201

    # Mesmo email
    res2 = client.post("/usuarios", json={
        "nome": "Outra Maria",
        "email": "maria@universidade.edu.br",
        "matricula": "20260003",
        "categoria": "visitante"
    })
    assert res2.status_code == 400
    assert "E-mail já cadastrado" in res2.json()["detail"]

    # Mesma matrícula
    res3 = client.post("/usuarios", json={
        "nome": "Outro João",
        "email": "outro@universidade.edu.br",
        "matricula": "20260002",
        "categoria": "visitante"
    })
    assert res3.status_code == 400
    assert "Matrícula já cadastrada" in res3.json()["detail"]

def test_crud_usuario(client):
    # Criar
    res = client.post("/usuarios", json={
        "nome": "Carlos Drummond",
        "email": "carlos@universidade.edu.br",
        "matricula": "20260010",
        "categoria": "visitante"
    })
    assert res.status_code == 201
    user_id = res.json()["id"]

    # Buscar
    res = client.get(f"/usuarios/{user_id}")
    assert res.status_code == 200
    assert res.json()["nome"] == "Carlos Drummond"

    # Atualizar
    res = client.put(f"/usuarios/{user_id}", json={
        "nome": "Carlos D. de Andrade",
        "categoria": "aluno"
    })
    assert res.status_code == 200
    assert res.json()["nome"] == "Carlos D. de Andrade"
    assert res.json()["categoria"] == "aluno"

    # Listar
    res = client.get("/usuarios")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # Deletar
    res = client.delete(f"/usuarios/{user_id}")
    assert res.status_code == 204

    # Buscar novamente
    res = client.get(f"/usuarios/{user_id}")
    assert res.status_code == 404
