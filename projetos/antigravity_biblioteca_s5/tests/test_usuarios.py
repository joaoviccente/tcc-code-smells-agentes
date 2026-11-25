def test_criar_usuario_sucesso(client):
    response = client.post(
        "/usuarios",
        json={
            "nome": "Carlos Andrade",
            "email": "carlos@uni.br",
            "matricula": "20240101",
            "categoria": "aluno",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "Carlos Andrade"
    assert data["email"] == "carlos@uni.br"
    assert data["matricula"] == "20240101"
    assert data["categoria"] == "aluno"
    assert data["situacao"] == "ativo"


def test_criar_usuario_email_duplicado(client):
    client.post(
        "/usuarios",
        json={
            "nome": "Carlos Andrade",
            "email": "carlos@uni.br",
            "matricula": "20240101",
            "categoria": "aluno",
        },
    )
    response = client.post(
        "/usuarios",
        json={
            "nome": "Outro Carlos",
            "email": "carlos@uni.br",
            "matricula": "20240102",
            "categoria": "professor",
        },
    )
    assert response.status_code == 409
    assert "já cadastrado" in response.json()["detail"]


def test_criar_usuario_matricula_duplicada(client):
    client.post(
        "/usuarios",
        json={
            "nome": "Carlos Andrade",
            "email": "carlos1@uni.br",
            "matricula": "20240101",
            "categoria": "aluno",
        },
    )
    response = client.post(
        "/usuarios",
        json={
            "nome": "Maria Silva",
            "email": "maria@uni.br",
            "matricula": "20240101",
            "categoria": "professor",
        },
    )
    assert response.status_code == 409
    assert "já cadastrada" in response.json()["detail"]


def test_listar_usuarios(client):
    client.post(
        "/usuarios",
        json={"nome": "A1", "email": "a1@u.br", "matricula": "M1", "categoria": "aluno"},
    )
    client.post(
        "/usuarios",
        json={"nome": "P1", "email": "p1@u.br", "matricula": "M2", "categoria": "professor"},
    )

    response = client.get("/usuarios")
    assert response.status_code == 200
    assert len(response.json()) == 2

    # Filtro por categoria
    resp_alunos = client.get("/usuarios?categoria=aluno")
    assert resp_alunos.status_code == 200
    assert len(resp_alunos.json()) == 1
    assert resp_alunos.json()[0]["nome"] == "A1"


def test_obter_e_atualizar_usuario(client):
    resp = client.post(
        "/usuarios",
        json={"nome": "João", "email": "joao@u.br", "matricula": "MJ", "categoria": "visitante"},
    )
    uid = resp.json()["id"]

    # Obter
    get_resp = client.get(f"/usuarios/{uid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["nome"] == "João"

    # Atualizar
    put_resp = client.put(f"/usuarios/{uid}", json={"nome": "João Atualizado"})
    assert put_resp.status_code == 200
    assert put_resp.json()["nome"] == "João Atualizado"


def test_deletar_usuario(client):
    resp = client.post(
        "/usuarios",
        json={"nome": "Para Deletar", "email": "del@u.br", "matricula": "MDEL", "categoria": "aluno"},
    )
    uid = resp.json()["id"]

    del_resp = client.delete(f"/usuarios/{uid}")
    assert del_resp.status_code == 204

    get_resp = client.get(f"/usuarios/{uid}")
    assert get_resp.status_code == 404
