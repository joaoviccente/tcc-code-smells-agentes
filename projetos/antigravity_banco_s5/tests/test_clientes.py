from fastapi import status


def test_criar_cliente_sucesso(client):
    payload = {
        "nome": "João da Silva",
        "cpf": "52998224725",  # CPF válido gerado
        "email": "joao.silva@exemplo.com",
        "categoria": "comum",
        "situacao": "ativo",
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "João da Silva"
    assert data["cpf"] == "529.982.247-25"
    assert data["categoria"] == "comum"
    assert data["situacao"] == "ativo"


def test_criar_cliente_cpf_invalido(client):
    payload = {
        "nome": "Carlos Invalido",
        "cpf": "11111111111",
        "email": "carlos@exemplo.com",
        "categoria": "premium",
    }
    response = client.post("/clientes", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_criar_cliente_cpf_duplicado(client):
    payload = {
        "nome": "Maria Santos",
        "cpf": "52998224725",
        "email": "maria@exemplo.com",
        "categoria": "premium",
    }
    res1 = client.post("/clientes", json=payload)
    assert res1.status_code == status.HTTP_201_CREATED

    payload2 = {
        "nome": "Outra Maria",
        "cpf": "52998224725",
        "email": "outra.maria@exemplo.com",
        "categoria": "comum",
    }
    res2 = client.post("/clientes", json=payload2)
    assert res2.status_code == status.HTTP_409_CONFLICT


def test_criar_cliente_email_duplicado(client):
    res1 = client.post("/clientes", json={
        "nome": "Cliente A",
        "cpf": "52998224725",
        "email": "mesmo.email@exemplo.com",
    })
    assert res1.status_code == status.HTTP_201_CREATED

    res2 = client.post("/clientes", json={
        "nome": "Cliente B",
        "cpf": "11144477735",  # Outro CPF válido
        "email": "mesmo.email@exemplo.com",
    })
    assert res2.status_code == status.HTTP_409_CONFLICT


def test_listar_e_filtrar_clientes(client):
    client.post("/clientes", json={
        "nome": "Empresa Alfa",
        "cpf": "52998224725",
        "email": "alfa@empresa.com",
        "categoria": "empresarial",
    })
    client.post("/clientes", json={
        "nome": "Cliente Beta",
        "cpf": "11144477735",
        "email": "beta@exemplo.com",
        "categoria": "comum",
    })

    res = client.get("/clientes?categoria=empresarial")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert len(data) == 1
    assert data[0]["nome"] == "Empresa Alfa"


def test_atualizar_cliente(client):
    res = client.post("/clientes", json={
        "nome": "Cliente Para Atualizar",
        "cpf": "52998224725",
        "email": "atualizar@exemplo.com",
        "categoria": "comum",
    })
    cliente_id = res.json()["id"]

    res_put = client.put(f"/clientes/{cliente_id}", json={
        "categoria": "premium",
        "situacao": "bloqueado",
    })
    assert res_put.status_code == status.HTTP_200_OK
    atualizado = res_put.json()
    assert atualizado["categoria"] == "premium"
    assert atualizado["situacao"] == "bloqueado"
