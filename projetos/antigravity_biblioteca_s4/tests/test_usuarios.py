from datetime import datetime, timedelta
from fastapi import status


def test_criar_usuario_sucesso(client):
    response = client.post(
        "/usuarios",
        json={
            "nome": "João Silva",
            "email": "joao@universidade.edu.br",
            "matricula": "A2024001",
            "categoria": "aluno",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "João Silva"
    assert data["email"] == "joao@universidade.edu.br"
    assert data["matricula"] == "A2024001"
    assert data["categoria"] == "aluno"
    assert data["situacao"] == "ativo"


def test_criar_usuario_duplicado_email_ou_matricula(client):
    client.post(
        "/usuarios",
        json={
            "nome": "João Silva",
            "email": "joao@universidade.edu.br",
            "matricula": "A2024001",
            "categoria": "aluno",
        },
    )

    # Mesmo email
    resp_email = client.post(
        "/usuarios",
        json={
            "nome": "Outro João",
            "email": "joao@universidade.edu.br",
            "matricula": "A2024002",
            "categoria": "aluno",
        },
    )
    assert resp_email.status_code == status.HTTP_409_CONFLICT

    # Mesma matrícula
    resp_mat = client.post(
        "/usuarios",
        json={
            "nome": "Outro João",
            "email": "outro@universidade.edu.br",
            "matricula": "A2024001",
            "categoria": "aluno",
        },
    )
    assert resp_mat.status_code == status.HTTP_409_CONFLICT


def test_listar_e_filtrar_usuarios(client):
    client.post(
        "/usuarios",
        json={
            "nome": "Aluno 1",
            "email": "aluno1@universidade.edu.br",
            "matricula": "AL01",
            "categoria": "aluno",
        },
    )
    client.post(
        "/usuarios",
        json={
            "nome": "Prof 1",
            "email": "prof1@universidade.edu.br",
            "matricula": "PR01",
            "categoria": "professor",
        },
    )

    resp = client.get("/usuarios")
    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.json()) == 2

    resp_aluno = client.get("/usuarios?categoria=aluno")
    assert resp_aluno.status_code == status.HTTP_200_OK
    assert len(resp_aluno.json()) == 1
    assert resp_aluno.json()[0]["categoria"] == "aluno"


def test_obter_e_atualizar_usuario(client):
    resp_create = client.post(
        "/usuarios",
        json={
            "nome": "Maria Santos",
            "email": "maria@universidade.edu.br",
            "matricula": "P2024001",
            "categoria": "professor",
        },
    )
    user_id = resp_create.json()["id"]

    resp_get = client.get(f"/usuarios/{user_id}")
    assert resp_get.status_code == status.HTTP_200_OK
    assert resp_get.json()["nome"] == "Maria Santos"

    resp_update = client.put(
        f"/usuarios/{user_id}",
        json={"nome": "Maria Santos Silva", "categoria": "professor"},
    )
    assert resp_update.status_code == status.HTTP_200_OK
    assert resp_update.json()["nome"] == "Maria Santos Silva"


def test_excluir_usuario(client):
    resp_create = client.post(
        "/usuarios",
        json={
            "nome": "Visitante 1",
            "email": "vis1@externo.com",
            "matricula": "V2024001",
            "categoria": "visitante",
        },
    )
    user_id = resp_create.json()["id"]

    resp_del = client.delete(f"/usuarios/{user_id}")
    assert resp_del.status_code == status.HTTP_204_NO_CONTENT

    resp_get = client.get(f"/usuarios/{user_id}")
    assert resp_get.status_code == status.HTTP_404_NOT_FOUND
