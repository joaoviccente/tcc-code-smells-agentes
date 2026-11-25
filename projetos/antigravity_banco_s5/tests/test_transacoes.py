from decimal import Decimal
from fastapi import status


def test_deposito_e_extrato(client):
    cli = client.post("/clientes", json={
        "nome": "Cliente Deposito",
        "cpf": "52998224725",
        "email": "deposito@exemplo.com",
    }).json()

    conta = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "4001",
        "limite_credito": 200.0,
    }).json()

    res_dep = client.post("/transacoes/deposito", json={
        "conta_id": conta["id"],
        "valor": 500.0,
        "descricao": "Depósito em dinheiro",
    })
    assert res_dep.status_code == status.HTTP_201_CREATED
    data_dep = res_dep.json()
    assert data_dep["tipo"] == "deposito"
    assert data_dep["estado"] == "efetivada"

    # Extrato
    res_ext = client.get(f"/contas/{conta['id']}/extrato")
    assert res_ext.status_code == status.HTTP_200_OK
    extrato = res_ext.json()
    assert Decimal(str(extrato["saldo_atual"])) == Decimal("500.00")
    assert Decimal(str(extrato["saldo_disponivel"])) == Decimal("700.00")  # 500 + 200 limite
    assert len(extrato["transacoes"]) == 1


def test_saque_limite_credito(client):
    # Regra 2: O saldo pode ficar negativo até o limite de crédito da conta.
    cli = client.post("/clientes", json={
        "nome": "Cliente Saque Limite",
        "cpf": "52998224725",
        "email": "saque.limite@exemplo.com",
    }).json()

    conta = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "4002",
        "limite_credito": 300.0,
    }).json()

    # Saldo 0, limite 300 -> saque de 200 é permitido (saldo fica -200)
    res_saque = client.post("/transacoes/saque", json={
        "conta_id": conta["id"],
        "valor": 200.0,
    })
    assert res_saque.status_code == status.HTTP_201_CREATED

    c_atual = client.get(f"/contas/{conta['id']}").json()
    assert Decimal(str(c_atual["saldo"])) == Decimal("-200.00")

    # Saque de mais 150 deve falhar, pois limite disponível restante é 100 (-200 + 300 = 100)
    res_falha = client.post("/transacoes/saque", json={
        "conta_id": conta["id"],
        "valor": 150.0,
    })
    assert res_falha.status_code == status.HTTP_400_BAD_REQUEST
    assert "Saldo insuficiente" in res_falha.json()["detail"]


def test_saque_limite_diario_categoria_comum(client):
    # Categoria Comum: limite diário de saque R$ 1.000,00
    cli = client.post("/clientes", json={
        "nome": "Cliente Comum",
        "cpf": "52998224725",
        "email": "comum.saque@exemplo.com",
        "categoria": "comum",
    }).json()

    conta = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "4003",
        "limite_credito": 2000.0,
    }).json()

    # Saque 1: R$ 600
    res1 = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 600.0})
    assert res1.status_code == status.HTTP_201_CREATED

    # Saque 2: R$ 400 (atinge 1.000)
    res2 = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 400.0})
    assert res2.status_code == status.HTTP_201_CREATED

    # Saque 3: R$ 50 (excede 1.000 diário) -> deve falhar
    res3 = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 50.0})
    assert res3.status_code == status.HTTP_400_BAD_REQUEST
    assert "Limite diário de saque excedido" in res3.json()["detail"]


def test_saque_conta_bloqueada_ou_cliente_bloqueado(client):
    cli = client.post("/clientes", json={
        "nome": "Cliente Bloqueado",
        "cpf": "52998224725",
        "email": "cli.bloq@exemplo.com",
        "situacao": "bloqueado",
    }).json()

    conta = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "4004",
        "limite_credito": 1000.0,
    }).json()

    res = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 50.0})
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "titular da conta está bloqueado" in res.json()["detail"]


def test_transferencia_mesmo_cliente_isenta(client):
    # Regra 3: Transferência entre contas do mesmo cliente é isenta de tarifa.
    cli = client.post("/clientes", json={
        "nome": "Titular Duas Contas",
        "cpf": "52998224725",
        "email": "duascontas@exemplo.com",
        "categoria": "comum",
    }).json()

    conta1 = client.post("/contas", json={"cliente_id": cli["id"], "numero": "5001"}).json()
    conta2 = client.post("/contas", json={"cliente_id": cli["id"], "numero": "5002"}).json()

    # Deposita 500 na conta 1
    client.post("/transacoes/deposito", json={"conta_id": conta1["id"], "valor": 500.0})

    # Transfere 200 da conta 1 para a conta 2
    res = client.post("/transacoes/transferencia", json={
        "conta_origem_id": conta1["id"],
        "conta_destino_id": conta2["id"],
        "valor": 200.0,
    })
    assert res.status_code == status.HTTP_201_CREATED

    c1 = client.get(f"/contas/{conta1['id']}").json()
    c2 = client.get(f"/contas/{conta2['id']}").json()
    assert Decimal(str(c1["saldo"])) == Decimal("300.00")
    assert Decimal(str(c2["saldo"])) == Decimal("200.00")

    # Tarifa registrada como isenta
    tarifas = client.get(f"/contas/{conta1['id']}/tarifas").json()
    assert len(tarifas) == 1
    assert tarifas[0]["estado"] == "isenta"


def test_transferencia_franquia_e_tarifa_excedente(client):
    # Categoria Comum: 3 transferências isentas por mês. Na 4ª, gera tarifa de R$ 10,00.
    cli1 = client.post("/clientes", json={
        "nome": "Cliente Origem",
        "cpf": "52998224725",
        "email": "origem@exemplo.com",
        "categoria": "comum",
    }).json()

    cli2 = client.post("/clientes", json={
        "nome": "Cliente Destino",
        "cpf": "11144477735",
        "email": "destino@exemplo.com",
        "categoria": "comum",
    }).json()

    conta1 = client.post("/contas", json={"cliente_id": cli1["id"], "numero": "6001"}).json()
    conta2 = client.post("/contas", json={"cliente_id": cli2["id"], "numero": "6002"}).json()

    # Deposita 1000 na conta 1
    client.post("/transacoes/deposito", json={"conta_id": conta1["id"], "valor": 1000.0})

    # Realiza 3 transferências de R$ 50 (isentas)
    for _ in range(3):
        res = client.post("/transacoes/transferencia", json={
            "conta_origem_id": conta1["id"],
            "conta_destino_id": conta2["id"],
            "valor": 50.0,
        })
        assert res.status_code == status.HTTP_201_CREATED

    # Saldo após 3 transferências: 1000 - 150 = 850
    c1 = client.get(f"/contas/{conta1['id']}").json()
    assert Decimal(str(c1["saldo"])) == Decimal("850.00")

    # 4ª transferência: esgotou a franquia -> cobra tarifa de R$ 10,00 (Regra 3)
    res4 = client.post("/transacoes/transferencia", json={
        "conta_origem_id": conta1["id"],
        "conta_destino_id": conta2["id"],
        "valor": 50.0,
    })
    assert res4.status_code == status.HTTP_201_CREATED

    # Saldo esperado: 850 - 50 (transferência) - 10 (tarifa) = 790
    c1_pos = client.get(f"/contas/{conta1['id']}").json()
    assert Decimal(str(c1_pos["saldo"])) == Decimal("790.00")

    # Verificar tarifas na conta
    tarifas = client.get(f"/contas/{conta1['id']}/tarifas").json()
    assert len(tarifas) == 4
    cobradas = [t for t in tarifas if t["estado"] == "cobrada"]
    isentas = [t for t in tarifas if t["estado"] == "isenta"]
    assert len(isentas) == 3
    assert len(cobradas) == 1
    assert Decimal(str(cobradas[0]["valor"])) == Decimal("10.00")


def test_transferencia_limite_por_operacao(client):
    # Comum: limite por transferência R$ 5.000,00
    cli = client.post("/clientes", json={
        "nome": "Cliente Limite Op",
        "cpf": "52998224725",
        "email": "limiteop@exemplo.com",
        "categoria": "comum",
    }).json()

    cli_dest = client.post("/clientes", json={
        "nome": "Destino",
        "cpf": "11144477735",
        "email": "destop@exemplo.com",
    }).json()

    c1 = client.post("/contas", json={"cliente_id": cli["id"], "numero": "7001", "limite_credito": 10000.0}).json()
    c2 = client.post("/contas", json={"cliente_id": cli_dest["id"], "numero": "7002"}).json()

    # Tentativa de transferir 5001 -> deve falhar
    res = client.post("/transacoes/transferencia", json={
        "conta_origem_id": c1["id"],
        "conta_destino_id": c2["id"],
        "valor": 5001.0,
    })
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "excede o limite por operação" in res.json()["detail"]


def test_estorno_transacao(client):
    # Regra 4: Uma transação efetivada pode ser estornada em até 24 horas.
    # O estorno reverte o saldo das contas envolvidas e registra uma nova transação do tipo estorno.
    cli = client.post("/clientes", json={
        "nome": "Cliente Estorno",
        "cpf": "52998224725",
        "email": "estorno@exemplo.com",
    }).json()

    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "8001"}).json()

    # 1. Depósito de 300
    dep = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 300.0}).json()
    assert Decimal(str(client.get(f"/contas/{conta['id']}").json()["saldo"])) == Decimal("300.00")

    # 2. Saque de 100
    saque = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 100.0}).json()
    assert Decimal(str(client.get(f"/contas/{conta['id']}").json()["saldo"])) == Decimal("200.00")

    # 3. Estorno do saque -> saldo deve voltar para 300
    res_estorno = client.post(f"/transacoes/{saque['id']}/estorno")
    assert res_estorno.status_code == status.HTTP_201_CREATED
    estorno_trans = res_estorno.json()
    assert estorno_trans["tipo"] == "estorno"
    assert estorno_trans["estado"] == "efetivada"
    assert estorno_trans["transacao_origem_id"] == saque["id"]

    # Saldo após estorno do saque
    c_pos = client.get(f"/contas/{conta['id']}").json()
    assert Decimal(str(c_pos["saldo"])) == Decimal("300.00")

    # Transação de saque original agora está estornada
    saque_atual = client.get(f"/transacoes/{saque['id']}").json()
    assert saque_atual["estado"] == "estornada"

    # Não pode estornar uma transação já estornada
    res_repetido = client.post(f"/transacoes/{saque['id']}/estorno")
    assert res_repetido.status_code == status.HTTP_400_BAD_REQUEST


def test_estorno_transferencia_completo(client):
    # Regra 4 com transferência entre duas contas
    cli1 = client.post("/clientes", json={
        "nome": "Cliente Origem Estorno",
        "cpf": "52998224725",
        "email": "origem.estorno@exemplo.com",
    }).json()
    cli2 = client.post("/clientes", json={
        "nome": "Cliente Destino Estorno",
        "cpf": "11144477735",
        "email": "destino.estorno@exemplo.com",
    }).json()

    c1 = client.post("/contas", json={"cliente_id": cli1["id"], "numero": "8501"}).json()
    c2 = client.post("/contas", json={"cliente_id": cli2["id"], "numero": "8502"}).json()

    # Deposita 1000 na conta 1
    client.post("/transacoes/deposito", json={"conta_id": c1["id"], "valor": 1000.0})

    # Transfere 400 da conta 1 para a conta 2
    transf = client.post("/transacoes/transferencia", json={
        "conta_origem_id": c1["id"],
        "conta_destino_id": c2["id"],
        "valor": 400.0,
    }).json()

    assert Decimal(str(client.get(f"/contas/{c1['id']}").json()["saldo"])) == Decimal("600.00")
    assert Decimal(str(client.get(f"/contas/{c2['id']}").json()["saldo"])) == Decimal("400.00")

    # Realiza estorno da transferência
    res_estorno = client.post(f"/transacoes/{transf['id']}/estorno")
    assert res_estorno.status_code == status.HTTP_201_CREATED

    # Saldos devem ser revertidos para 1000 e 0
    assert Decimal(str(client.get(f"/contas/{c1['id']}").json()["saldo"])) == Decimal("1000.00")
    assert Decimal(str(client.get(f"/contas/{c2['id']}").json()["saldo"])) == Decimal("0.00")


def test_limites_categoria_empresarial(client):
    # Empresarial: limite diário de saque R$ 20.000,00; limite por transferência R$ 200.000,00
    cli = client.post("/clientes", json={
        "nome": "Mega Corp",
        "cpf": "99988877714",
        "email": "financeiro@megacorp.com",
        "categoria": "empresarial",
    }).json()

    cli_dest = client.post("/clientes", json={
        "nome": "Fornecedor",
        "cpf": "52998224725",
        "email": "contato@fornecedor.com",
    }).json()

    c_emp = client.post("/contas", json={"cliente_id": cli["id"], "numero": "8601", "limite_credito": 500000.0}).json()
    c_dest = client.post("/contas", json={"cliente_id": cli_dest["id"], "numero": "8602"}).json()

    # Saque até R$ 20.000,00 permitido
    res_saque1 = client.post("/transacoes/saque", json={"conta_id": c_emp["id"], "valor": 20000.0})
    assert res_saque1.status_code == status.HTTP_201_CREATED

    # Saque adicional no mesmo dia ultrapassa R$ 20.000,00 -> erro
    res_saque2 = client.post("/transacoes/saque", json={"conta_id": c_emp["id"], "valor": 1.0})
    assert res_saque2.status_code == status.HTTP_400_BAD_REQUEST

    # Transferência de R$ 200.000,00 permitida
    res_transf = client.post("/transacoes/transferencia", json={
        "conta_origem_id": c_emp["id"],
        "conta_destino_id": c_dest["id"],
        "valor": 200000.0,
    })
    assert res_transf.status_code == status.HTTP_201_CREATED

    # Transferência acima de R$ 200.000,00 negada
    res_transf_falha = client.post("/transacoes/transferencia", json={
        "conta_origem_id": c_emp["id"],
        "conta_destino_id": c_dest["id"],
        "valor": 200001.0,
    })
    assert res_transf_falha.status_code == status.HTTP_400_BAD_REQUEST


def test_estorno_apos_24_horas_falha(client):
    # Regra 4: Uma transação efetivada pode ser estornada em até 24 horas.
    from tests.conftest import TestingSessionLocal
    from app.models.transacao import Transacao
    from datetime import datetime, timedelta, timezone

    cli = client.post("/clientes", json={
        "nome": "Cliente Estorno 24h",
        "cpf": "52998224725",
        "email": "estorno24h@exemplo.com",
    }).json()

    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "8701"}).json()
    dep = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 500.0}).json()

    # Modificar a data da transação para 25 horas no passado
    db = TestingSessionLocal()
    t = db.query(Transacao).filter(Transacao.id == dep["id"]).first()
    t.data = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=25)
    db.commit()
    db.close()

    # Tentar estorno
    res = client.post(f"/transacoes/{dep['id']}/estorno")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "24 horas" in res.json()["detail"]


