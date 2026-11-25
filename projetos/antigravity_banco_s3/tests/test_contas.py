def test_criar_conta_sucesso(client):
    cli = client.post(
        "/clientes",
        json={
            "nome": "Cliente Conta",
            "cpf": "12345678909",
            "email": "conta@example.com",
            "categoria": "comum",
        },
    ).json()

    conta_payload = {
        "cliente_id": cli["id"],
        "numero": "1001-X",
        "tipo": "corrente",
        "saldo_inicial": 500.0,
        "limite_credito": 1000.0,
    }
    res = client.post("/contas", json=conta_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["numero"] == "1001-X"
    assert float(data["saldo"]) == 500.0
    assert float(data["limite_credito"]) == 1000.0
    assert data["estado"] == "ativa"


def test_criar_conta_numero_duplicado(client):
    cli = client.post(
        "/clientes",
        json={
            "nome": "Cliente 1",
            "cpf": "12345678909",
            "email": "c1@example.com",
            "categoria": "comum",
        },
    ).json()

    conta_payload = {
        "cliente_id": cli["id"],
        "numero": "2001-A",
        "tipo": "corrente",
        "saldo_inicial": 0.0,
        "limite_credito": 500.0,
    }
    res1 = client.post("/contas", json=conta_payload)
    assert res1.status_code == 201

    res2 = client.post("/contas", json=conta_payload)
    assert res2.status_code == 409


def test_encerrar_conta_saldo_nao_zero_falha(client):
    cli = client.post(
        "/clientes",
        json={
            "nome": "Cliente Saldo",
            "cpf": "12345678909",
            "email": "saldo@example.com",
            "categoria": "comum",
        },
    ).json()

    conta = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "3001-B",
            "tipo": "corrente",
            "saldo_inicial": 150.0,
            "limite_credito": 0.0,
        },
    ).json()

    # Tenta encerrar conta com saldo positivo
    res_encerrar = client.post(f"/contas/{conta['id']}/encerrar")
    assert res_encerrar.status_code == 400
    assert "saldo zero" in res_encerrar.json()["detail"].lower()


def test_encerrar_conta_sucesso(client):
    cli = client.post(
        "/clientes",
        json={
            "nome": "Cliente Zero",
            "cpf": "12345678909",
            "email": "zero@example.com",
            "categoria": "comum",
        },
    ).json()

    conta = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "4001-C",
            "tipo": "corrente",
            "saldo_inicial": 0.0,
            "limite_credito": 0.0,
        },
    ).json()

    # Cria cartão vinculado
    cartao = client.post(
        "/cartoes",
        json={"conta_id": conta["id"], "numero": "4001-CARTAO-1", "limite": 1000.0},
    ).json()
    assert cartao["estado"] == "ativo"

    # Encerra conta
    res_encerrar = client.post(f"/contas/{conta['id']}/encerrar")
    assert res_encerrar.status_code == 200
    assert res_encerrar.json()["estado"] == "encerrada"

    # Verifica se cartão foi cancelado (Regra 7)
    res_cartao = client.get(f"/cartoes/{cartao['id']}")
    assert res_cartao.json()["estado"] == "cancelado"
