import pytest
from tests.conftest import gerar_cpf_valido


@pytest.fixture
def conta_id(client):
    cpf = gerar_cpf_valido(601)
    cli = client.post(
        "/clientes",
        json={"nome": "Cli Cartao", "cpf": cpf, "email": "cartao@test.com", "categoria": "comum"},
    ).json()["id"]
    cta = client.post(
        "/contas",
        json={"cliente_id": cli, "numero": "CTA-CARTAO", "tipo": "corrente", "limite_credito": "100.00"},
    ).json()["id"]
    return cta


def test_criar_cartao(client, conta_id):
    res = client.post(
        "/cartoes",
        json={"conta_id": conta_id, "numero": "4002-8922-0000-1111", "limite": "2500.00"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["conta_id"] == conta_id
    assert data["numero"] == "4002-8922-0000-1111"
    assert data["limite"] == "2500.00"
    assert data["estado"] == "ativo"


def test_duplicidade_numero_cartao(client, conta_id):
    client.post(
        "/cartoes",
        json={"conta_id": conta_id, "numero": "SAME-NUM-CARD", "limite": "1000.00"},
    )
    res2 = client.post(
        "/cartoes",
        json={"conta_id": conta_id, "numero": "SAME-NUM-CARD", "limite": "1000.00"},
    )
    assert res2.status_code == 400
    assert "número" in res2.json()["detail"]


def test_bloquear_e_cancelar_cartao(client, conta_id):
    c = client.post(
        "/cartoes",
        json={"conta_id": conta_id, "numero": "CARD-BLOQ", "limite": "1000.00"},
    ).json()["id"]

    # Bloquear
    res_bloq = client.put(f"/cartoes/{c}", json={"estado": "bloqueado"})
    assert res_bloq.status_code == 200
    assert res_bloq.json()["estado"] == "bloqueado"

    # Cancelar via DELETE
    res_canc = client.delete(f"/cartoes/{c}")
    assert res_canc.status_code == 200
    assert res_canc.json()["estado"] == "cancelado"
