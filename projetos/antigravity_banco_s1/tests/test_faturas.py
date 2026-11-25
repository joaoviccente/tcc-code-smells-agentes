from datetime import date, timedelta
from decimal import Decimal
import pytest
from tests.conftest import gerar_cpf_valido


@pytest.fixture
def conta_e_cartao(client):
    cli = client.post(
        "/clientes",
        json={"nome": "Titular Fatura", "cpf": gerar_cpf_valido(901), "email": "fat@test.com", "categoria": "comum"},
    ).json()["id"]
    cta = client.post(
        "/contas",
        json={"cliente_id": cli, "numero": "CTA-FATURA", "limite_credito": "1000.00"},
    ).json()["id"]
    cartao = client.post(
        "/cartoes",
        json={"conta_id": cta, "numero": "5555-4444-3333-2222", "limite": "3000.00"},
    ).json()["id"]
    return {"cliente_id": cli, "conta_id": cta, "cartao_id": cartao}


def test_criar_e_listar_fatura(client, conta_e_cartao):
    cartao_id = conta_e_cartao["cartao_id"]
    vencimento = date.today() + timedelta(days=20)

    res = client.post(
        f"/cartoes/{cartao_id}/faturas",
        json={"mes_referencia": "2026-11", "valor": "350.50", "data_vencimento": str(vencimento)},
    )
    assert res.status_code == 201
    fatura_id = res.json()["id"]

    res_list = client.get(f"/cartoes/{cartao_id}/faturas")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1
    assert res_list.json()[0]["id"] == fatura_id


def test_pagamento_fatura_debito_em_conta(client, conta_e_cartao):
    cartao_id = conta_e_cartao["cartao_id"]
    conta_id = conta_e_cartao["conta_id"]
    vencimento = date.today() + timedelta(days=10)

    # Deposita dinheiro na conta
    client.post("/transacoes/deposito", json={"conta_id": conta_id, "valor": "500.00"})

    fatura = client.post(
        f"/cartoes/{cartao_id}/faturas",
        json={"mes_referencia": "2026-11", "valor": "200.00", "data_vencimento": str(vencimento)},
    ).json()["id"]

    # Realiza pagamento debitando da conta corrente
    res_pag = client.post(
        f"/faturas/{fatura}/pagamento",
        json={"valor_pago": "200.00", "conta_id": conta_id},
    )
    assert res_pag.status_code == 200
    assert res_pag.json()["estado"] == "paga"
    assert res_pag.json()["valor_pago"] == "200.00"
    assert res_pag.json()["data_pagamento"] is not None

    # Saldo da conta deve ter sido debitado de 200.00 (500 -> 300)
    saldo_conta = client.get(f"/contas/{conta_id}").json()["saldo"]
    assert saldo_conta == "300.00"
