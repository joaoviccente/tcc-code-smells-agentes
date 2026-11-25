from decimal import Decimal


def test_deposito_sucesso(client):
    cli = client.post(
        "/clientes",
        json={
            "nome": "Cliente Deposito",
            "cpf": "12345678909",
            "email": "dep@example.com",
            "categoria": "comum",
        },
    ).json()

    conta = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "DEP-01",
            "tipo": "corrente",
            "saldo_inicial": 100.0,
            "limite_credito": 0.0,
        },
    ).json()

    res_dep = client.post(
        "/transacoes/deposito", json={"conta_id": conta["id"], "valor": 250.0}
    )
    assert res_dep.status_code == 201
    assert float(res_dep.json()["valor"]) == 250.0

    res_conta = client.get(f"/contas/{conta['id']}")
    assert float(res_conta.json()["saldo"]) == 350.0


def test_saque_limite_diario_comum(client):
    # Categoria Comum: limite diário de saque R$ 1.000,00
    cli = client.post(
        "/clientes",
        json={
            "nome": "Cliente Comum",
            "cpf": "12345678909",
            "email": "comum@example.com",
            "categoria": "comum",
        },
    ).json()

    conta = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "SAQ-COMUM",
            "tipo": "corrente",
            "saldo_inicial": 5000.0,
            "limite_credito": 500.0,
        },
    ).json()

    # Saque de 800.0 deve ser aceito
    res1 = client.post(
        "/transacoes/saque", json={"conta_id": conta["id"], "valor": 800.0}
    )
    assert res1.status_code == 201

    # Saque de mais 300.0 deve ser negado (800 + 300 = 1100 > 1000)
    res2 = client.post(
        "/transacoes/saque", json={"conta_id": conta["id"], "valor": 300.0}
    )
    assert res2.status_code == 400
    assert "limite diário de saque excedido" in res2.json()["detail"].lower()


def test_saque_limite_credito_negativo(client):
    # Regra 2: O saldo pode ficar negativo até o limite de crédito da conta. Abaixo disso, a operação é negada.
    cli = client.post(
        "/clientes",
        json={
            "nome": "Cliente Credito",
            "cpf": "12345678909",
            "email": "credito@example.com",
            "categoria": "comum",
        },
    ).json()

    conta = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "SAQ-CREDITO",
            "tipo": "corrente",
            "saldo_inicial": 100.0,
            "limite_credito": 300.0,  # Total disponível = 400.0
        },
    ).json()

    # Saque de 350.0 (deixa saldo em -250.0, dentro do limite de 300)
    res1 = client.post(
        "/transacoes/saque", json={"conta_id": conta["id"], "valor": 350.0}
    )
    assert res1.status_code == 201

    conta_updated = client.get(f"/contas/{conta['id']}").json()
    assert float(conta_updated["saldo"]) == -250.0
    assert conta_updated["saldo_negativo_desde"] is not None

    # Novo saque de 60.0 (excederia o limite de 300: -250 - 60 = -310)
    res2 = client.post(
        "/transacoes/saque", json={"conta_id": conta["id"], "valor": 60.0}
    )
    assert res2.status_code == 400
    assert "saldo insuficiente" in res2.json()["detail"].lower()


def test_transferencia_mesmo_cliente_isenta(client):
    # Regra 3: Transferência entre contas do mesmo cliente é isenta de tarifa.
    cli = client.post(
        "/clientes",
        json={
            "nome": "Cliente Mesmo",
            "cpf": "12345678909",
            "email": "mesmo@example.com",
            "categoria": "comum",
        },
    ).json()

    c1 = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "ORIGEM-1",
            "tipo": "corrente",
            "saldo_inicial": 1000.0,
            "limite_credito": 0.0,
        },
    ).json()

    c2 = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "DESTINO-1",
            "tipo": "corrente",
            "saldo_inicial": 100.0,
            "limite_credito": 0.0,
        },
    ).json()

    res = client.post(
        "/transacoes/transferencia",
        json={
            "conta_origem_id": c1["id"],
            "conta_destino_id": c2["id"],
            "valor": 400.0,
        },
    )
    assert res.status_code == 201

    # Verifica saldos: c1 deve ser 600.0 (sem taxa), c2 deve ser 500.0
    assert float(client.get(f"/contas/{c1['id']}").json()["saldo"]) == 600.0
    assert float(client.get(f"/contas/{c2['id']}").json()["saldo"]) == 500.0

    # Verifica que tarifa registrada é ISENTA
    tarifas = client.get(f"/contas/{c1['id']}/tarifas").json()
    assert len(tarifas) == 1
    assert tarifas[0]["estado"] == "isenta"


def test_transferencia_franquia_e_tarifa_excedente(client):
    # Categoria Comum: 3 transações isentas por mês
    cli1 = client.post(
        "/clientes",
        json={
            "nome": "Cliente Comum Tarifa",
            "cpf": "12345678909",
            "email": "comumtar@example.com",
            "categoria": "comum",
        },
    ).json()

    cli2 = client.post(
        "/clientes",
        json={
            "nome": "Cliente Terceiro",
            "cpf": "98765432100",
            "email": "terceiro@example.com",
            "categoria": "comum",
        },
    ).json()

    c_origem = client.post(
        "/contas",
        json={
            "cliente_id": cli1["id"],
            "numero": "CORIG-01",
            "tipo": "corrente",
            "saldo_inicial": 2000.0,
            "limite_credito": 0.0,
        },
    ).json()

    c_destino = client.post(
        "/contas",
        json={
            "cliente_id": cli2["id"],
            "numero": "CDEST-01",
            "tipo": "corrente",
            "saldo_inicial": 0.0,
            "limite_credito": 0.0,
        },
    ).json()

    # Faz 3 transferências de 100.0 (todas dentro da franquia de 3 isentas)
    for _ in range(3):
        res = client.post(
            "/transacoes/transferencia",
            json={
                "conta_origem_id": c_origem["id"],
                "conta_destino_id": c_destino["id"],
                "valor": 100.0,
            },
        )
        assert res.status_code == 201

    # Saldo após 3 transferências: 2000 - 300 = 1700.0
    assert float(client.get(f"/contas/{c_origem['id']}").json()["saldo"]) == 1700.0

    # A 4ª transferência esgota a franquia e gera tarifa de R$ 10.00
    res4 = client.post(
        "/transacoes/transferencia",
        json={
            "conta_origem_id": c_origem["id"],
            "conta_destino_id": c_destino["id"],
            "valor": 100.0,
        },
    )
    assert res4.status_code == 201

    # Saldo após 4ª transferência: 1700 - 100 (transf) - 10 (tarifa) = 1590.0
    assert float(client.get(f"/contas/{c_origem['id']}").json()["saldo"]) == 1590.0

    # Verifica tarifas
    tarifas = client.get(f"/contas/{c_origem['id']}/tarifas").json()
    assert len(tarifas) == 4
    # 3 isentas e 1 cobrada
    cobradas = [t for t in tarifas if t["estado"] == "cobrada"]
    isentas = [t for t in tarifas if t["estado"] == "isenta"]
    assert len(cobradas) == 1
    assert len(isentas) == 3


def test_estorno_sucesso(client):
    # Regra 4: Estorno reverte o saldo das contas envolvidas e registra nova transação do tipo estorno
    cli1 = client.post(
        "/clientes",
        json={
            "nome": "Cliente Estorno 1",
            "cpf": "12345678909",
            "email": "est1@example.com",
            "categoria": "premium",
        },
    ).json()

    cli2 = client.post(
        "/clientes",
        json={
            "nome": "Cliente Estorno 2",
            "cpf": "98765432100",
            "email": "est2@example.com",
            "categoria": "premium",
        },
    ).json()

    c1 = client.post(
        "/contas",
        json={
            "cliente_id": cli1["id"],
            "numero": "EST-C1",
            "tipo": "corrente",
            "saldo_inicial": 1000.0,
            "limite_credito": 0.0,
        },
    ).json()

    c2 = client.post(
        "/contas",
        json={
            "cliente_id": cli2["id"],
            "numero": "EST-C2",
            "tipo": "corrente",
            "saldo_inicial": 500.0,
            "limite_credito": 0.0,
        },
    ).json()

    # Realiza transferência de 300.0 de c1 para c2
    tx_transf = client.post(
        "/transacoes/transferencia",
        json={
            "conta_origem_id": c1["id"],
            "conta_destino_id": c2["id"],
            "valor": 300.0,
        },
    ).json()

    assert float(client.get(f"/contas/{c1['id']}").json()["saldo"]) == 700.0
    assert float(client.get(f"/contas/{c2['id']}").json()["saldo"]) == 800.0

    # Realiza estorno da transferência
    res_estorno = client.post(f"/transacoes/{tx_transf['id']}/estorno")
    assert res_estorno.status_code == 201
    tx_est = res_estorno.json()
    assert tx_est["tipo"] == "estorno"
    assert float(tx_est["valor"]) == 300.0
    assert tx_est["transacao_origem_id"] == tx_transf["id"]

    # Saldos devem ter retornado ao valor original!
    assert float(client.get(f"/contas/{c1['id']}").json()["saldo"]) == 1000.0
    assert float(client.get(f"/contas/{c2['id']}").json()["saldo"]) == 500.0

    # Tentar estornar novamente deve falhar
    res_repetido = client.post(f"/transacoes/{tx_transf['id']}/estorno")
    assert res_repetido.status_code == 400
