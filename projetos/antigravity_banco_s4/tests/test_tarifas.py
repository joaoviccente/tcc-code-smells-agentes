from tests.conftest import gerar_cpf


def test_tarifas_mensais_por_categoria(client):
    """
    Tarifa mensal por categoria:
    Comum: R$ 30,00
    Premium: R$ 0,00 (sem tarifa)
    Empresarial: R$ 120,00
    """
    cli_c = client.post("/clientes", json={"nome": "Cli Comum Tarifa", "cpf": gerar_cpf(601), "email": "ctar@ex.com", "categoria": "comum"}).json()
    conta_c = client.post("/contas", json={"cliente_id": cli_c["id"], "numero": "60001-1", "tipo": "corrente", "saldo_inicial": 200.0}).json()

    cli_p = client.post("/clientes", json={"nome": "Cli Prem Tarifa", "cpf": gerar_cpf(602), "email": "ptar@ex.com", "categoria": "premium"}).json()
    conta_p = client.post("/contas", json={"cliente_id": cli_p["id"], "numero": "60002-2", "tipo": "corrente", "saldo_inicial": 200.0}).json()

    cli_e = client.post("/clientes", json={"nome": "Cli Emp Tarifa", "cpf": gerar_cpf(603), "email": "etar@ex.com", "categoria": "empresarial"}).json()
    conta_e = client.post("/contas", json={"cliente_id": cli_e["id"], "numero": "60003-3", "tipo": "corrente", "saldo_inicial": 200.0}).json()

    # Executa cobrança de mensalidades para todas as contas
    res = client.post("/tarifas/cobrar-mensalidades")
    assert res.status_code == 200
    data = res.json()
    assert data["contas_processadas"] == 3
    assert data["tarifas_cobradas"] == 2  # Comum (30) + Empresarial (120)
    assert float(data["valor_total_arrecadado"]) == 150.0  # 30 + 120

    # Verifica saldo da conta Comum: 200 - 30 = 170
    c_check = client.get(f"/contas/{conta_c['id']}").json()
    assert float(c_check["saldo"]) == 170.0
    tarifas_c = client.get(f"/contas/{conta_c['id']}/tarifas").json()
    assert len(tarifas_c) == 1
    assert float(tarifas_c[0]["valor"]) == 30.0
    assert tarifas_c[0]["estado"] == "cobrada"

    # Verifica saldo da conta Premium: 200 - 0 = 200
    p_check = client.get(f"/contas/{conta_p['id']}").json()
    assert float(p_check["saldo"]) == 200.0
    tarifas_p = client.get(f"/contas/{conta_p['id']}/tarifas").json()
    assert len(tarifas_p) == 1
    assert float(tarifas_p[0]["valor"]) == 0.0
    assert tarifas_p[0]["estado"] == "isenta"

    # Verifica saldo da conta Empresarial: 200 - 120 = 80
    e_check = client.get(f"/contas/{conta_e['id']}").json()
    assert float(e_check["saldo"]) == 80.0
    tarifas_e = client.get(f"/contas/{conta_e['id']}/tarifas").json()
    assert len(tarifas_e) == 1
    assert float(tarifas_e[0]["valor"]) == 120.0
    assert tarifas_e[0]["estado"] == "cobrada"
