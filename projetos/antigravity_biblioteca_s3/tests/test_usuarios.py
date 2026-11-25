def test_crud_usuario(client):
    # 1. Criar usuário
    payload = {
        "nome": "João da Silva",
        "email": "joao@universidade.edu.br",
        "matricula": "2024001",
        "categoria": "aluno",
        "situacao": "ativo"
    }
    response = client.post("/usuarios", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == payload["nome"]
    assert data["email"] == payload["email"]
    assert data["matricula"] == payload["matricula"]
    assert data["categoria"] == "aluno"
    assert data["situacao"] == "ativo"

    usuario_id = data["id"]

    # 2. Obter por ID
    get_res = client.get(f"/usuarios/{usuario_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == usuario_id

    # 3. Listar usuários
    list_res = client.get("/usuarios")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # 4. Atualizar usuário
    update_payload = {"nome": "João da Silva Sauro"}
    put_res = client.put(f"/usuarios/{usuario_id}", json=update_payload)
    assert put_res.status_code == 200
    assert put_res.json()["nome"] == "João da Silva Sauro"

    # 5. Excluir usuário
    del_res = client.delete(f"/usuarios/{usuario_id}")
    assert del_res.status_code == 204

    # Verificar exclusão
    assert client.get(f"/usuarios/{usuario_id}").status_code == 404


def test_duplicidade_email_e_matricula(client):
    client.post("/usuarios", json={
        "nome": "Carlos",
        "email": "carlos@universidade.edu.br",
        "matricula": "1001",
        "categoria": "professor"
    })

    # Mesmo email
    res_email = client.post("/usuarios", json={
        "nome": "Carlos 2",
        "email": "carlos@universidade.edu.br",
        "matricula": "1002",
        "categoria": "professor"
    })
    assert res_email.status_code == 409

    # Mesma matrícula
    res_mat = client.post("/usuarios", json={
        "nome": "Carlos 3",
        "email": "carlos3@universidade.edu.br",
        "matricula": "1001",
        "categoria": "professor"
    })
    assert res_mat.status_code == 409


def test_validacao_categoria_invalida(client):
    res = client.post("/usuarios", json={
        "nome": "Invalido",
        "email": "inv@universidade.edu.br",
        "matricula": "9999",
        "categoria": "coordenador"
    })
    assert res.status_code == 422
