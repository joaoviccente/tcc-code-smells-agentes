import pytest


def test_criar_aluno_sucesso(client):
    response = client.post("/alunos", json={
        "nome": "Carlos Silva",
        "matricula": "2026001",
        "email": "carlos@universidade.edu.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "Carlos Silva"
    assert data["matricula"] == "2026001"
    assert data["categoria"] == "graduacao"
    assert data["situacao"] == "ativo"


def test_criar_aluno_matricula_duplicada(client):
    client.post("/alunos", json={
        "nome": "Carlos Silva",
        "matricula": "2026001",
        "email": "carlos1@universidade.edu.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    })
    response = client.post("/alunos", json={
        "nome": "Outro Aluno",
        "matricula": "2026001",
        "email": "outro@universidade.edu.br",
        "categoria": "pos",
        "situacao": "ativo"
    })
    assert response.status_code == 409


def test_criar_aluno_email_duplicado(client):
    client.post("/alunos", json={
        "nome": "Carlos Silva",
        "matricula": "2026001",
        "email": "carlos@universidade.edu.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    })
    response = client.post("/alunos", json={
        "nome": "Outro Aluno",
        "matricula": "2026002",
        "email": "carlos@universidade.edu.br",
        "categoria": "pos",
        "situacao": "ativo"
    })
    assert response.status_code == 409


def test_obter_aluno(client):
    res_create = client.post("/alunos", json={
        "nome": "Ana Lima",
        "matricula": "2026003",
        "email": "ana@universidade.edu.br",
        "categoria": "pos",
        "situacao": "ativo"
    })
    aluno_id = res_create.json()["id"]

    response = client.get(f"/alunos/{aluno_id}")
    assert response.status_code == 200
    assert response.json()["nome"] == "Ana Lima"


def test_obter_aluno_inexistente(client):
    response = client.get("/alunos/9999")
    assert response.status_code == 404


def test_atualizar_aluno(client):
    res_create = client.post("/alunos", json={
        "nome": "Beatriz Santos",
        "matricula": "2026004",
        "email": "beatriz@universidade.edu.br",
        "categoria": "especial",
        "situacao": "ativo"
    })
    aluno_id = res_create.json()["id"]

    response = client.put(f"/alunos/{aluno_id}", json={
        "nome": "Beatriz Santos da Silva",
        "situacao": "trancado"
    })
    assert response.status_code == 200
    assert response.json()["nome"] == "Beatriz Santos da Silva"
    assert response.json()["situacao"] == "trancado"


def test_remover_aluno(client):
    res_create = client.post("/alunos", json={
        "nome": "Marcos Silva",
        "matricula": "2026005",
        "email": "marcos@universidade.edu.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    })
    aluno_id = res_create.json()["id"]

    del_res = client.delete(f"/alunos/{aluno_id}")
    assert del_res.status_code == 204

    get_res = client.get(f"/alunos/{aluno_id}")
    assert get_res.status_code == 404
