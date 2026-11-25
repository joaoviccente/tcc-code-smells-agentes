import pytest
from fastapi import status


def test_criar_cliente_sucesso(client):
    payload = {
        "nome": "Carlos Silva",
        "cpf": "45678901249",
        "email": "carlos@example.com",
        "categoria": "comum",
        "situacao": "ativo"
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "Carlos Silva"
    assert data["cpf"] == "45678901249"
    assert data["email"] == "carlos@example.com"
    assert data["categoria"] == "comum"
    assert data["situacao"] == "ativo"


def test_criar_cliente_cpf_invalido(client):
    payload = {
        "nome": "Carlos Silva",
        "cpf": "11111111111",  # Dígitos repetidos
        "email": "carlos2@example.com",
        "categoria": "comum",
        "situacao": "ativo"
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_criar_cliente_email_invalido(client):
    payload = {
        "nome": "Carlos Silva",
        "cpf": "45678901249",
        "email": "email_invalido",
        "categoria": "comum",
        "situacao": "ativo"
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_criar_cliente_cpf_duplicado(client, cliente_comum):
    payload = {
        "nome": "Outro João",
        "cpf": cliente_comum.cpf,
        "email": "outro_joao@example.com",
        "categoria": "comum",
        "situacao": "ativo"
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "CPF" in response.json()["detail"]


def test_criar_cliente_email_duplicado(client, cliente_comum):
    payload = {
        "nome": "Outro João",
        "cpf": "45678901249",
        "email": cliente_comum.email,
        "categoria": "comum",
        "situacao": "ativo"
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "e-mail" in response.json()["detail"]


def test_listar_clientes_com_filtro(client, cliente_comum, cliente_premium):
    response = client.get("/clientes")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 2

    # Filtro por categoria
    response_premium = client.get("/clientes?categoria=premium")
    assert response_premium.status_code == status.HTTP_200_OK
    dados = response_premium.json()
    assert len(dados) == 1
    assert dados[0]["id"] == cliente_premium.id


def test_obter_cliente_por_id(client, cliente_comum):
    response = client.get(f"/clientes/{cliente_comum.id}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == cliente_comum.id

    response_404 = client.get("/clientes/99999")
    assert response_404.status_code == status.HTTP_404_NOT_FOUND


def test_atualizar_cliente(client, cliente_comum):
    payload = {
        "nome": "João da Silva Atualizado",
        "categoria": "premium"
    }
    response = client.put(f"/clientes/{cliente_comum.id}", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["nome"] == "João da Silva Atualizado"
    assert data["categoria"] == "premium"


def test_deletar_cliente_sucesso(client):
    # Cria cliente sem conta
    payload = {
        "nome": "Sem Conta",
        "cpf": "56789012303",
        "email": "semconta@example.com",
    }
    resp = client.post("/clientes", json=payload)
    cid = resp.json()["id"]

    response = client.delete(f"/clientes/{cid}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verifica exclusão
    assert client.get(f"/clientes/{cid}").status_code == status.HTTP_404_NOT_FOUND


def test_deletar_cliente_com_saldo_falha(client, conta_comum):
    response = client.delete(f"/clientes/{conta_comum.cliente_id}")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "saldo" in response.json()["detail"].lower()
