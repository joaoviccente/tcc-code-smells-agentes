from datetime import date, timedelta
from tests.conftest import gerar_cpf


def test_regra_5_juros_por_categoria(client):
    """
    Regra 5: Fatura não paga até o vencimento passa ao estado atrasada
    e acumula juros conforme a categoria:
    Comum: 8% ao mês
    Premium: 5% ao mês
    Empresarial: 3% ao mês
    """
    # 1. Comum (8% ao mês)
    cli_c = client.post("/clientes", json={"nome": "Cli Comum Fat", "cpf": gerar_cpf(501), "email": "cfat@ex.com", "categoria": "comum"}).json()
    conta_c = client.post("/contas", json={"cliente_id": cli_c["id"], "numero": "50001-1", "tipo": "corrente"}).json()
    cartao_c = client.post("/cartoes", json={"conta_id": conta_c["id"], "numero": "5000111122223333", "limite": 5000.0}).json()

    vencimento_30d = str(date.today() - timedelta(days=30))
    fat_c = client.post("/faturas", json={
        "cartao_id": cartao_c["id"],
        "mes_referencia": "2026-10",
        "valor": 1000.0,
        "data_vencimento": vencimento_30d,
    }).json()

    assert fat_c["estado"] == "atrasada"
    # 1000 * 0.08 * (30/30) = 80.00
    assert float(fat_c["juros_acumulados"]) == 80.0
    assert float(fat_c["valor_total_devido"]) == 1080.0

    # 2. Premium (5% ao mês)
    cli_p = client.post("/clientes", json={"nome": "Cli Prem Fat", "cpf": gerar_cpf(502), "email": "pfat@ex.com", "categoria": "premium"}).json()
    conta_p = client.post("/contas", json={"cliente_id": cli_p["id"], "numero": "50002-2", "tipo": "corrente"}).json()
    cartao_p = client.post("/cartoes", json={"conta_id": conta_p["id"], "numero": "5000222233334444", "limite": 10000.0}).json()

    fat_p = client.post("/faturas", json={
        "cartao_id": cartao_p["id"],
        "mes_referencia": "2026-10",
        "valor": 1000.0,
        "data_vencimento": vencimento_30d,
    }).json()

    assert fat_p["estado"] == "atrasada"
    # 1000 * 0.05 * (30/30) = 50.00
    assert float(fat_p["juros_acumulados"]) == 50.0
    assert float(fat_p["valor_total_devido"]) == 1050.0

    # 3. Empresarial (3% ao mês)
    cli_e = client.post("/clientes", json={"nome": "Cli Emp Fat", "cpf": gerar_cpf(503), "email": "efat@ex.com", "categoria": "empresarial"}).json()
    conta_e = client.post("/contas", json={"cliente_id": cli_e["id"], "numero": "50003-3", "tipo": "corrente"}).json()
    cartao_e = client.post("/cartoes", json={"conta_id": conta_e["id"], "numero": "5000333344445555", "limite": 20000.0}).json()

    fat_e = client.post("/faturas", json={
        "cartao_id": cartao_e["id"],
        "mes_referencia": "2026-10",
        "valor": 1000.0,
        "data_vencimento": vencimento_30d,
    }).json()

    assert fat_e["estado"] == "atrasada"
    # 1000 * 0.03 * (30/30) = 30.00
    assert float(fat_e["juros_acumulados"]) == 30.0
    assert float(fat_e["valor_total_devido"]) == 1030.0


def test_regra_5_bloqueio_cartao_apos_10_dias_atraso(client):
    """Regra 5: Após 10 dias de atraso, o cartão é bloqueado."""
    cli = client.post("/clientes", json={"nome": "Bloq Cartao User", "cpf": gerar_cpf(504), "email": "bcartao@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "50004-4", "tipo": "corrente"}).json()
    
    # Cartão 1: atraso de 5 dias -> continua ativo
    cartao1 = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "5000555566667777", "limite": 2000.0}).json()
    client.post("/faturas", json={
        "cartao_id": cartao1["id"],
        "mes_referencia": "2026-10",
        "valor": 200.0,
        "data_vencimento": str(date.today() - timedelta(days=5)),
    })
    c1_check = client.get(f"/cartoes/{cartao1['id']}").json()
    assert c1_check["estado"] == "ativo"

    # Cartão 2: atraso de 11 dias -> bloqueado!
    cartao2 = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "5000888899990000", "limite": 2000.0}).json()
    client.post("/faturas", json={
        "cartao_id": cartao2["id"],
        "mes_referencia": "2026-10",
        "valor": 300.0,
        "data_vencimento": str(date.today() - timedelta(days=11)),
    })
    c2_check = client.get(f"/cartoes/{cartao2['id']}").json()
    assert c2_check["estado"] == "bloqueado"


def test_pagamento_fatura_e_quitacao(client):
    cli = client.post("/clientes", json={"nome": "Pag User", "cpf": gerar_cpf(505), "email": "pag@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "50005-5", "tipo": "corrente"}).json()
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "5000123412341234", "limite": 3000.0}).json()

    fat = client.post("/faturas", json={
        "cartao_id": cartao["id"],
        "mes_referencia": "2026-11",
        "valor": 500.0,
        "data_vencimento": str(date.today() + timedelta(days=10)),
    }).json()

    # Pagamento parcial de 200
    res1 = client.post(f"/faturas/{fat['id']}/pagamento", json={"valor": 200.0})
    assert res1.status_code == 200
    assert float(res1.json()["valor_pago"]) == 200.0
    assert res1.json()["estado"] == "aberta"

    # Pagamento restante de 300
    res2 = client.post(f"/faturas/{fat['id']}/pagamento", json={"valor": 300.0})
    assert res2.status_code == 200
    assert float(res2.json()["valor_pago"]) == 500.0
    assert res2.json()["estado"] == "paga"
    assert res2.json()["data_pagamento"] is not None
