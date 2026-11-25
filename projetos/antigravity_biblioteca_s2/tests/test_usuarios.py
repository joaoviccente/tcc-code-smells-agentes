def test_criar_usuario(client):
    response = client.post(
        "/usuarios",
        json={
            "nome": "João da Silva",
            "email": "joao@universidade.edu.br",
            "matricula": "2024001",
            "categoria": "aluno",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "João da Silva"
    assert data["email"] == "joao@universidade.edu.br"
    assert data["matricula"] == "2024001"
    assert data["categoria"] == "aluno"
    assert data["situacao"] == "ativo"


def test_criar_usuario_duplicado(client):
    payload = {
        "nome": "Maria Souza",
        "email": "maria@universidade.edu.br",
        "matricula": "2024002",
        "categoria": "professor",
    }
    res1 = client.post("/usuarios", json=payload)
    assert res1.status_code == 201

    # Email duplicado
    res2 = client.post(
        "/usuarios",
        json={
            "nome": "Outra Maria",
            "email": "maria@universidade.edu.br",
            "matricula": "2024003",
            "categoria": "aluno",
        },
    )
    assert res2.status_code == 409

    # Matrícula duplicada
    res3 = client.post(
        "/usuarios",
        json={
            "nome": "Outra Maria",
            "email": "maria2@universidade.edu.br",
            "matricula": "2024002",
            "categoria": "aluno",
        },
    )
    assert res3.status_code == 409


def test_obter_e_listar_usuarios(client):
    client.post(
        "/usuarios",
        json={
            "nome": "Carlos Pereira",
            "email": "carlos@universidade.edu.br",
            "matricula": "2024004",
            "categoria": "visitante",
        },
    )

    res_list = client.get("/usuarios")
    assert res_list.status_code == 200
    usuarios = res_list.json()
    assert len(usuarios) == 1
    usuario_id = usuarios[0]["id"]

    res_get = client.get(f"/usuarios/{usuario_id}")
    assert res_get.status_code == 200
    assert res_get.json()["matricula"] == "2024004"


def test_atualizar_usuario(client):
    res = client.post(
        "/usuarios",
        json={
            "nome": "Ana Lima",
            "email": "ana@universidade.edu.br",
            "matricula": "2024005",
            "categoria": "aluno",
        },
    )
    user_id = res.json()["id"]

    res_put = client.put(
        f"/usuarios/{user_id}",
        json={"nome": "Ana Lima Santos", "categoria": "professor"},
    )
    assert res_put.status_code == 200
    data = res_put.json()
    assert data["nome"] == "Ana Lima Santos"
    assert data["categoria"] == "professor"


def test_deletar_usuario(client):
    res = client.post(
        "/usuarios",
        json={
            "nome": "Bruno Costa",
            "email": "bruno@universidade.edu.br",
            "matricula": "2024006",
            "categoria": "visitante",
        },
    )
    user_id = res.json()["id"]

    res_del = client.delete(f"/usuarios/{user_id}")
    assert res_del.status_code == 204

    res_get = client.get(f"/usuarios/{user_id}")
    assert res_get.status_code == 404
