import pytest
from tests.conftest import gerar_cpf_valido


def test_criar_cliente_com_sucesso(client):
    cpf = gerar_cpf_valido(100)
    response = client.post(
        "/clientes",
        json={
            "nome": "João Silva",
            "cpf": cpf,
            "email": "joao.silva@exemplo.com",
            "categoria": "comum",
            "situacao": "ativo",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["nome"] == "João Silva"
    assert data["cpf"] == cpf
    assert data["email"] == "joao.silva@exemplo.com"
    assert data["categoria"] == "comum"
    assert data["situacao"] == "ativo"
    assert "id" in data


def test_validacao_cpf_invalido(client):
    # CPF com dígitos verificadores incorretos
    response = client.post(
        "/clientes",
        json={
            "nome": "Invalido Silva",
            "cpf": "12345678900",
            "email": "invalido@exemplo.com",
            "categoria": "comum",
        },
    )
    assert response.status_code == 422


def test_validacao_cpf_todos_digitos_iguais(client):
    response = client.post(
        "/clientes",
        json={
            "nome": "Digitos Iguais",
            "cpf": "11111111111",
            "email": "iguais@exemplo.com",
            "categoria": "comum",
        },
    )
    assert response.status_code == 422


def test_duplicidade_de_cpf_e_email(client):
    cpf = gerar_cpf_valido(101)
    payload = {
        "nome": "Maria Santos",
        "cpf": cpf,
        "email": "maria@exemplo.com",
        "categoria": "premium",
    }
    res1 = client.post("/clientes", json=payload)
    assert res1.status_code == 201

    # Tentativa com mesmo CPF
    res2 = client.post(
        "/clientes",
        json={
            "nome": "Outra Maria",
            "cpf": cpf,
            "email": "outramaria@exemplo.com",
            "categoria": "premium",
        },
    )
    assert res2.status_code == 400
    assert "CPF" in res2.json()["detail"]

    # Tentativa com mesmo E-mail
    res3 = client.post(
        "/clientes",
        json={
            "nome": "Terceira Maria",
            "cpf": gerar_cpf_valido(102),
            "email": "maria@exemplo.com",
            "categoria": "empresarial",
        },
    )
    assert res3.status_code == 400
    assert "e-mail" in res3.json()["detail"]


def test_listar_e_filtrar_clientes(client):
    cpf1 = gerar_cpf_valido(201)
    cpf2 = gerar_cpf_valido(202)
    client.post("/clientes", json={"nome": "Cli 1", "cpf": cpf1, "email": "c1@test.com", "categoria": "comum"})
    client.post("/clientes", json={"nome": "Cli 2", "cpf": cpf2, "email": "c2@test.com", "categoria": "empresarial"})

    res_all = client.get("/clientes")
    assert res_all.status_code == 200
    assert len(res_all.json()) >= 2

    res_filter = client.get("/clientes?categoria=empresarial")
    assert res_filter.status_code == 200
    assert len(res_filter.json()) == 1
    assert res_filter.json()[0]["nome"] == "Cli 2"


def test_atualizar_cliente(client):
    cpf = gerar_cpf_valido(301)
    res_create = client.post(
        "/clientes",
        json={"nome": "Pedro Inicial", "cpf": cpf, "email": "pedro@test.com", "categoria": "comum"},
    )
    cliente_id = res_create.json()["id"]

    res_update = client.put(
        f"/clientes/{cliente_id}",
        json={"nome": "Pedro Atualizado", "categoria": "premium", "situacao": "bloqueado"},
    )
    assert res_update.status_code == 200
    data = res_update.json()
    assert data["nome"] == "Pedro Atualizado"
    assert data["categoria"] == "premium"
    assert data["situacao"] == "bloqueado"


def test_deletar_cliente_sem_contas(client):
    cpf = gerar_cpf_valido(401)
    res_create = client.post(
        "/clientes",
        json={"nome": "Deletar Me", "cpf": cpf, "email": "del@test.com", "categoria": "comum"},
    )
    cliente_id = res_create.json()["id"]

    res_del = client.delete(f"/clientes/{cliente_id}")
    assert res_del.status_code == 204

    res_get = client.get(f"/clientes/{cliente_id}")
    assert res_get.status_code == 404
