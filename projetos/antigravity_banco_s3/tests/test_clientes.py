def test_criar_cliente_sucesso(client):
    payload = {
        "nome": "João Silva",
        "cpf": "12345678909",
        "email": "joao@example.com",
        "categoria": "comum",
        "situacao": "ativo",
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "João Silva"
    assert data["cpf"] == "123.456.789-09"
    assert data["categoria"] == "comum"
    assert data["situacao"] == "ativo"


def test_criar_cliente_cpf_invalido(client):
    payload = {
        "nome": "Carlos Invalido",
        "cpf": "11111111111",
        "email": "carlos@example.com",
        "categoria": "comum",
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == 422


def test_criar_cliente_cpf_duplicado(client):
    payload = {
        "nome": "Maria Santos",
        "cpf": "12345678909",
        "email": "maria@example.com",
        "categoria": "premium",
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == 201

    payload_dup = {
        "nome": "Outra Maria",
        "cpf": "123.456.789-09",
        "email": "maria2@example.com",
        "categoria": "empresarial",
    }
    response2 = client.post("/clientes", json=payload_dup)
    assert response2.status_code == 409


def test_listar_e_obter_cliente(client):
    payload = {
        "nome": "Cliente Teste",
        "cpf": "12345678909",
        "email": "teste@example.com",
        "categoria": "empresarial",
    }
    res = client.post("/clientes", json=payload)
    cliente_id = res.json()["id"]

    res_list = client.get("/clientes")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1

    res_get = client.get(f"/clientes/{cliente_id}")
    assert res_get.status_code == 200
    assert res_get.json()["nome"] == "Cliente Teste"


def test_atualizar_cliente(client):
    payload = {
        "nome": "Nome Original",
        "cpf": "12345678909",
        "email": "original@example.com",
        "categoria": "comum",
    }
    res = client.post("/clientes", json=payload)
    cliente_id = res.json()["id"]

    update_payload = {"nome": "Nome Alterado", "categoria": "premium"}
    res_update = client.put(f"/clientes/{cliente_id}", json=update_payload)
    assert res_update.status_code == 200
    assert res_update.json()["nome"] == "Nome Alterado"
    assert res_update.json()["categoria"] == "premium"
