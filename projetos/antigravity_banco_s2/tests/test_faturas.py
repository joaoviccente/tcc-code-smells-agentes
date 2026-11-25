from datetime import date, timedelta
from decimal import Decimal
from fastapi import status
from app.config import EstadoFatura, EstadoCartao


def test_criar_fatura_sucesso(client, cartao_comum):
    payload = {
        "cartao_id": cartao_comum.id,
        "mes_referencia": "2026-11",
        "valor": "1000.00",
        "data_vencimento": "2026-11-25",
    }
    response = client.post("/faturas", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["cartao_id"] == cartao_comum.id
    assert Decimal(data["valor"]) == Decimal("1000.00")
    assert data["estado"] == "aberta"
    assert data["dias_atraso"] == 0


def test_pagar_fatura_sucesso(client, cartao_comum):
    payload = {
        "cartao_id": cartao_comum.id,
        "mes_referencia": "2026-11",
        "valor": "500.00",
        "data_vencimento": "2026-11-25",
    }
    fatura_id = client.post("/faturas", json=payload).json()["id"]

    # Pagar fatura integralmente
    pag_resp = client.post(f"/faturas/{fatura_id}/pagamento", json={})
    assert pag_resp.status_code == status.HTTP_200_OK
    assert pag_resp.json()["estado"] == "paga"
    assert Decimal(pag_resp.json()["valor"]) == Decimal("0.00")

    # Tentativa de pagar novamente deve falhar
    pag_resp2 = client.post(f"/faturas/{fatura_id}/pagamento", json={})
    assert pag_resp2.status_code == status.HTTP_400_BAD_REQUEST


def test_regra_5_juros_e_bloqueio_cartao_atraso(client, db, cartao_comum):
    # Cliente Comum -> Taxa de juros: 8% ao mês (0.08)
    # Fatura de R$ 1000,00 vencida há 15 dias (> 10 dias de atraso)
    hoje = date.today()
    vencimento_atrasado = hoje - timedelta(days=15)

    payload = {
        "cartao_id": cartao_comum.id,
        "mes_referencia": "2026-10",
        "valor": "1000.00",
        "data_vencimento": vencimento_atrasado.isoformat(),
    }
    fatura_resp = client.post("/faturas", json=payload)
    assert fatura_resp.status_code == status.HTTP_201_CREATED
    data = fatura_resp.json()

    # Estado deve ser atrasada
    assert data["estado"] == "atrasada"
    assert data["dias_atraso"] == 15

    # Juros calculados: 1000 * (0.08 * 15 / 30) = 1000 * 0.04 = R$ 40,00
    assert Decimal(data["juros_acumulados"]) == Decimal("40.00")
    assert Decimal(data["valor"]) == Decimal("1040.00")

    # Como atraso é de 15 dias (> 10 dias), o cartão deve ter sido bloqueado!
    resp_cartao = client.get(f"/cartoes/{cartao_comum.id}")
    assert resp_cartao.json()["estado"] == "bloqueado"


def test_processar_atrasos_endpoint(client, cartao_comum):
    # Cria fatura com vencimento para amanhã (ainda aberta)
    amanha = date.today() + timedelta(days=1)
    payload = {
        "cartao_id": cartao_comum.id,
        "mes_referencia": "2026-11",
        "valor": "200.00",
        "data_vencimento": amanha.isoformat(),
    }
    client.post("/faturas", json=payload)

    # Simula passagem de tempo chamando a rotina com data futura de 12 dias após vencimento
    data_futura = amanha + timedelta(days=12)
    resp_rotina = client.post(f"/faturas/processar-atrasos?data_ref={data_futura.isoformat()}")
    assert resp_rotina.status_code == status.HTTP_200_OK
    data = resp_rotina.json()
    assert data["cartoes_bloqueados"] >= 1
    assert data["faturas_atualizadas"] >= 1
