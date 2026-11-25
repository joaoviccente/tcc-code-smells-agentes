from datetime import datetime, timedelta
from tests.conftest import gerar_cpf
from app.models.transacao import Transacao


def test_deposito_sucesso(client):
    cli = client.post("/clientes", json={"nome": "Dep User", "cpf": gerar_cpf(401), "email": "dep@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "40001-1", "tipo": "corrente", "saldo_inicial": 100.0}).json()

    res = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 250.0, "descricao": "Depósito teste"})
    assert res.status_code == 201
    data = res.json()
    assert data["tipo"] == "deposito"
    assert float(data["valor"]) == 250.0
    assert data["estado"] == "efetivada"

    # Verifica saldo atualizado na conta
    c = client.get(f"/contas/{conta['id']}").json()
    assert float(c["saldo"]) == 350.0


def test_regra_1_saque_limite_diario_comum(client):
    """Categoria Comum: limite diário de saque R$ 1.000,00"""
    cli = client.post("/clientes", json={"nome": "Comum Saque", "cpf": gerar_cpf(402), "email": "csaque@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "40002-2", "tipo": "corrente", "saldo_inicial": 2000.0}).json()

    # Primeiro saque de 700.00 -> OK
    res1 = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 700.0})
    assert res1.status_code == 201

    # Segundo saque de 300.00 -> OK (acumulou 1000.00)
    res2 = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 300.0})
    assert res2.status_code == 201

    # Terceiro saque de 1.00 -> Deve ser negado por exceder o limite diário da categoria (1.000,00)
    res3 = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 1.0})
    assert res3.status_code == 400
    assert "limite diário de saque excedido" in res3.json()["detail"].lower()


def test_regra_1_saque_limites_outras_categorias(client):
    """Premium (R$ 5.000,00) e Empresarial (R$ 20.000,00)"""
    # Premium
    cli_p = client.post("/clientes", json={"nome": "Prem", "cpf": gerar_cpf(403), "email": "prem@ex.com", "categoria": "premium"}).json()
    conta_p = client.post("/contas", json={"cliente_id": cli_p["id"], "numero": "40003-3", "tipo": "corrente", "saldo_inicial": 10000.0}).json()

    res_p1 = client.post("/transacoes/saque", json={"conta_id": conta_p["id"], "valor": 5000.0})
    assert res_p1.status_code == 201
    res_p2 = client.post("/transacoes/saque", json={"conta_id": conta_p["id"], "valor": 0.01})
    assert res_p2.status_code == 400
    assert "limite diário de saque excedido" in res_p2.json()["detail"].lower()

    # Empresarial
    cli_e = client.post("/clientes", json={"nome": "Emp", "cpf": gerar_cpf(404), "email": "emp@ex.com", "categoria": "empresarial"}).json()
    conta_e = client.post("/contas", json={"cliente_id": cli_e["id"], "numero": "40004-4", "tipo": "corrente", "saldo_inicial": 30000.0}).json()

    res_e1 = client.post("/transacoes/saque", json={"conta_id": conta_e["id"], "valor": 20000.0})
    assert res_e1.status_code == 201
    res_e2 = client.post("/transacoes/saque", json={"conta_id": conta_e["id"], "valor": 1.0})
    assert res_e2.status_code == 400
    assert "limite diário de saque excedido" in res_e2.json()["detail"].lower()


def test_regra_2_saldo_negativo_ate_limite_de_credito(client):
    """Saldo pode ficar negativo até o limite de crédito. Abaixo disso, é negado."""
    cli = client.post("/clientes", json={"nome": "Limite User", "cpf": gerar_cpf(405), "email": "lim@ex.com", "categoria": "comum"}).json()
    # Saldo 100, limite de credito 400 -> total disponível 500
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "40005-5", "tipo": "corrente", "saldo_inicial": 100.0, "limite_de_credito": 400.0}).json()

    # Saque de 500 -> OK (saldo fica -400)
    res1 = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 500.0})
    assert res1.status_code == 201

    c = client.get(f"/contas/{conta['id']}").json()
    assert float(c["saldo"]) == -400.0

    # Tentativa de sacar mais 0.01 -> Negado por insuficiência de saldo+limite
    res2 = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 0.01})
    assert res2.status_code == 400
    assert "saldo insuficiente" in res2.json()["detail"].lower()


def test_regra_1_transferencia_limite_por_operacao(client):
    """Limites por transferência: Comum 5.000, Premium 50.000, Empresarial 200.000"""
    cli_c = client.post("/clientes", json={"nome": "Comum Transf", "cpf": gerar_cpf(406), "email": "ctransf@ex.com", "categoria": "comum"}).json()
    conta_c1 = client.post("/contas", json={"cliente_id": cli_c["id"], "numero": "40006-1", "tipo": "corrente", "saldo_inicial": 10000.0}).json()
    conta_c2 = client.post("/contas", json={"cliente_id": cli_c["id"], "numero": "40006-2", "tipo": "corrente", "saldo_inicial": 0.0}).json()

    # Comum tentando transferir 5000.01 -> Negado
    res = client.post("/transacoes/transferencia", json={
        "conta_origem_id": conta_c1["id"],
        "conta_destino_id": conta_c2["id"],
        "valor": 5000.01,
    })
    assert res.status_code == 400
    assert "limite por transferência" in res.json()["detail"].lower()

    # Comum transferindo exatamente 5000.00 -> OK
    res_ok = client.post("/transacoes/transferencia", json={
        "conta_origem_id": conta_c1["id"],
        "conta_destino_id": conta_c2["id"],
        "valor": 5000.00,
    })
    assert res_ok.status_code == 201


def test_regra_3_transferencia_mesmo_cliente_isenta(client):
    """Transferência entre contas do mesmo cliente é isenta de tarifa."""
    cli = client.post("/clientes", json={"nome": "Mesmo Cliente", "cpf": gerar_cpf(407), "email": "mesmo@ex.com", "categoria": "comum"}).json()
    c1 = client.post("/contas", json={"cliente_id": cli["id"], "numero": "40007-1", "tipo": "corrente", "saldo_inicial": 1000.0}).json()
    c2 = client.post("/contas", json={"cliente_id": cli["id"], "numero": "40007-2", "tipo": "corrente", "saldo_inicial": 0.0}).json()

    res = client.post("/transacoes/transferencia", json={
        "conta_origem_id": c1["id"],
        "conta_destino_id": c2["id"],
        "valor": 100.0,
    })
    assert res.status_code == 201

    # Verificar tarifas da conta de origem
    tarifas = client.get(f"/contas/{c1['id']}/tarifas").json()
    assert len(tarifas) == 1
    assert tarifas[0]["estado"] == "isenta"
    assert float(tarifas[0]["valor"]) == 0.0

    # Saldo de origem deve ser exatamente 900.0 (sem desconto de tarifa)
    c1_atualizada = client.get(f"/contas/{c1['id']}").json()
    assert float(c1_atualizada["saldo"]) == 900.0


def test_regra_3_franquia_e_cobranca_tarifa_clientes_diferentes(client):
    """
    Categoria Comum: 3 transações isentas por mês.
    A 4ª transação entre clientes diferentes deve gerar cobrança de tarifa.
    """
    cli_a = client.post("/clientes", json={"nome": "Cli A", "cpf": gerar_cpf(408), "email": "clia@ex.com", "categoria": "comum"}).json()
    cli_b = client.post("/clientes", json={"nome": "Cli B", "cpf": gerar_cpf(409), "email": "clib@ex.com", "categoria": "comum"}).json()

    c_origem = client.post("/contas", json={"cliente_id": cli_a["id"], "numero": "40008-1", "tipo": "corrente", "saldo_inicial": 1000.0}).json()
    c_destino = client.post("/contas", json={"cliente_id": cli_b["id"], "numero": "40008-2", "tipo": "corrente", "saldo_inicial": 0.0}).json()

    # 3 transferências gratuitas
    for _ in range(3):
        res = client.post("/transacoes/transferencia", json={
            "conta_origem_id": c_origem["id"],
            "conta_destino_id": c_destino["id"],
            "valor": 50.0,
        })
        assert res.status_code == 201

    # Saldo devedor após 3 transações de 50 = 1000 - 150 = 850
    c_origem_check = client.get(f"/contas/{c_origem['id']}").json()
    assert float(c_origem_check["saldo"]) == 850.0

    # 4ª transferência: esgotada a franquia, deve cobrar tarifa de R$ 10,00
    res4 = client.post("/transacoes/transferencia", json={
        "conta_origem_id": c_origem["id"],
        "conta_destino_id": c_destino["id"],
        "valor": 50.0,
    })
    assert res4.status_code == 201

    # Saldo deve ser 850 - 50 (transf) - 10 (tarifa) = 790.00
    c_origem_apos4 = client.get(f"/contas/{c_origem['id']}").json()
    assert float(c_origem_apos4["saldo"]) == 790.0

    # Verifica se a tarifa cobrada foi registrada
    tarifas = client.get(f"/contas/{c_origem['id']}/tarifas").json()
    assert len(tarifas) == 4
    # A última tarifa gerada deve ser cobrada no valor de 10.00
    tarifas_cobradas = [t for t in tarifas if t["estado"] == "cobrada"]
    assert len(tarifas_cobradas) == 1
    assert float(tarifas_cobradas[0]["valor"]) == 10.0


def test_regra_4_estorno_saque_sucesso(client):
    """Estorno em até 24h reverte saldo e cria transação de estorno."""
    cli = client.post("/clientes", json={"nome": "Estorno User", "cpf": gerar_cpf(410), "email": "est@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "40010-1", "tipo": "corrente", "saldo_inicial": 500.0}).json()

    # Realiza saque de 200
    saque = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 200.0}).json()

    c_apos_saque = client.get(f"/contas/{conta['id']}").json()
    assert float(c_apos_saque["saldo"]) == 300.0

    # Realiza estorno do saque
    res_estorno = client.post(f"/transacoes/{saque['id']}/estorno")
    assert res_estorno.status_code == 200
    estorno_data = res_estorno.json()
    assert estorno_data["tipo"] == "estorno"
    assert estorno_data["transacao_origem_id"] == saque["id"]

    # Saldo deve ter retornado para 500.0
    c_apos_estorno = client.get(f"/contas/{conta['id']}").json()
    assert float(c_apos_estorno["saldo"]) == 500.0

    # Transação original deve estar estornada
    extrato = client.get(f"/contas/{conta['id']}/extrato").json()
    t_orig = next(t for t in extrato["transacoes"] if t["id"] == saque["id"])
    assert t_orig["estado"] == "estornada"


def test_regra_4_estorno_apos_24_horas_rejeitado(client, db_session):
    """Estorno de transação com mais de 24 horas deve ser negado."""
    cli = client.post("/clientes", json={"nome": "Estorno Expirado", "cpf": gerar_cpf(411), "email": "exp@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "40011-1", "tipo": "corrente", "saldo_inicial": 500.0}).json()

    saque = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 100.0}).json()

    # Modifica data da transação no banco para 25 horas atrás
    t_db = db_session.query(Transacao).filter(Transacao.id == saque["id"]).first()
    t_db.data = datetime.utcnow() - timedelta(hours=25)
    db_session.commit()

    # Tentativa de estorno deve falhar
    res = client.post(f"/transacoes/{saque['id']}/estorno")
    assert res.status_code == 400
    assert "prazo para estorno expirado" in res.json()["detail"].lower()


def test_extrato_conta(client):
    cli = client.post("/clientes", json={"nome": "Extrato User", "cpf": gerar_cpf(412), "email": "ext@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "40012-1", "tipo": "corrente", "saldo_inicial": 200.0, "limite_de_credito": 300.0}).json()

    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 100.0})
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 50.0})

    res = client.get(f"/contas/{conta['id']}/extrato")
    assert res.status_code == 200
    data = res.json()
    assert float(data["saldo_atual"]) == 250.0
    assert float(data["limite_de_credito"]) == 300.0
    assert float(data["saldo_disponivel"]) == 550.0
    assert data["total_transacoes"] == 2
