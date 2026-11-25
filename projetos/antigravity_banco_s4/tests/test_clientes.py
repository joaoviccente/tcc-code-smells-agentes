import pytest
from tests.conftest import gerar_cpf


def test_criar_cliente_sucesso(client):
    cpf = gerar_cpf(101)
    payload = {
        "nome": "João Silva",
        "cpf": cpf,
        "email": "joao.silva@example.com",
        "categoria": "comum",
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "João Silva"
    assert data["cpf"] == cpf
    assert data["categoria"] == "comum"
    assert data["situacao"] == "ativo"


def test_criar_cliente_cpf_duplicado(client):
    cpf = gerar_cpf(102)
    payload = {
        "nome": "Maria Santos",
        "cpf": cpf,
        "email": "maria.santos@example.com",
        "categoria": "premium",
    }
    response1 = client.post("/clientes", json=payload)
    assert response1.status_code == 201

    payload2 = {
        "nome": "Outra Maria",
        "cpf": cpf,
        "email": "outra.maria@example.com",
        "categoria": "comum",
    }
    response2 = client.post("/clientes", json=payload2)
    assert response2.status_code == 409
    assert "CPF já cadastrado" in response2.json()["detail"]


def test_criar_cliente_email_duplicado(client):
    payload1 = {
        "nome": "Carlos Drummond",
        "cpf": gerar_cpf(103),
        "email": "carlos@example.com",
        "categoria": "empresarial",
    }
    response1 = client.post("/clientes", json=payload1)
    assert response1.status_code == 201

    payload2 = {
        "nome": "Carlos Andrade",
        "cpf": gerar_cpf(104),
        "email": "carlos@example.com",
        "categoria": "comum",
    }
    response2 = client.post("/clientes", json=payload2)
    assert response2.status_code == 409
    assert "E-mail já cadastrado" in response2.json()["detail"]


def test_criar_cliente_cpf_invalido(client):
    payload = {
        "nome": "Teste Invalido",
        "cpf": "11111111111",
        "email": "invalido@example.com",
        "categoria": "comum",
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == 422


def test_listar_clientes_e_filtros(client):
    client.post("/clientes", json={"nome": "A Comum", "cpf": gerar_cpf(105), "email": "a@ex.com", "categoria": "comum"})
    client.post("/clientes", json={"nome": "B Premium", "cpf": gerar_cpf(106), "email": "b@ex.com", "categoria": "premium"})
    client.post("/clientes", json={"nome": "C Empresarial", "cpf": gerar_cpf(107), "email": "c@ex.com", "categoria": "empresarial"})

    res_todos = client.get("/clientes")
    assert res_todos.status_code == 200
    assert len(res_todos.json()) == 3

    res_premium = client.get("/clientes?categoria=premium")
    assert res_premium.status_code == 200
    assert len(res_premium.json()) == 1
    assert res_premium.json()[0]["nome"] == "B Premium"


def test_obter_cliente_por_id(client):
    cpf = gerar_cpf(108)
    criado = client.post("/clientes", json={"nome": "Ana Lima", "cpf": cpf, "email": "ana@ex.com", "categoria": "comum"}).json()

    res = client.get(f"/clientes/{criado['id']}")
    assert res.status_code == 200
    assert res.json()["nome"] == "Ana Lima"

    res_404 = client.get("/clientes/999999")
    assert res_404.status_code == 404


def test_atualizar_cliente(client):
    criado = client.post("/clientes", json={"nome": "Original", "cpf": gerar_cpf(109), "email": "orig@ex.com", "categoria": "comum"}).json()

    res = client.put(f"/clientes/{criado['id']}", json={"nome": "Modificado", "categoria": "premium", "situacao": "bloqueado"})
    assert res.status_code == 200
    atualizado = res.json()
    assert atualizado["nome"] == "Modificado"
    assert atualizado["categoria"] == "premium"
    assert atualizado["situacao"] == "bloqueado"


def test_deletar_cliente_sem_contas(client):
    criado = client.post("/clientes", json={"nome": "Deletar", "cpf": gerar_cpf(110), "email": "del@ex.com", "categoria": "comum"}).json()
    res = client.delete(f"/clientes/{criado['id']}")
    assert res.status_code == 204

    res_check = client.get(f"/clientes/{criado['id']}")
    assert res_check.status_code == 404
