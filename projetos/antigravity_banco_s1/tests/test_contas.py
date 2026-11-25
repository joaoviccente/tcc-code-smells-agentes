import pytest
from tests.conftest import gerar_cpf_valido


@pytest.fixture
def cliente_id(client):
    cpf = gerar_cpf_valido(501)
    res = client.post(
        "/clientes",
        json={"nome": "Titular Conta", "cpf": cpf, "email": "titular@test.com", "categoria": "comum"},
    )
    return res.json()["id"]


def test_criar_conta_com_sucesso(client, cliente_id):
    res = client.post(
        "/contas",
        json={
            "cliente_id": cliente_id,
            "numero": "12345-6",
            "tipo": "corrente",
            "limite_credito": "500.00",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["cliente_id"] == cliente_id
    assert data["numero"] == "12345-6"
    assert data["saldo"] == "0.00"
    assert data["limite_credito"] == "500.00"
    assert data["estado"] == "ativa"


def test_duplicidade_numero_conta(client, cliente_id):
    client.post(
        "/contas",
        json={"cliente_id": cliente_id, "numero": "99999-9", "tipo": "corrente", "limite_credito": "0.00"},
    )
    res2 = client.post(
        "/contas",
        json={"cliente_id": cliente_id, "numero": "99999-9", "tipo": "poupanca", "limite_credito": "0.00"},
    )
    assert res2.status_code == 400
    assert "número" in res2.json()["detail"]


def test_cliente_inexistente_ao_criar_conta(client):
    res = client.post(
        "/contas",
        json={"cliente_id": 9999, "numero": "00000-0", "tipo": "corrente", "limite_credito": "0.00"},
    )
    assert res.status_code == 404


def test_regra_7_encerramento_conta_com_saldo_diferente_de_zero(client, cliente_id):
    # Cria conta
    res_conta = client.post(
        "/contas",
        json={"cliente_id": cliente_id, "numero": "33333-3", "tipo": "corrente", "limite_credito": "500.00"},
    )
    conta_id = res_conta.json()["id"]

    # Realiza depósito (saldo > 0)
    client.post("/transacoes/deposito", json={"conta_id": conta_id, "valor": "100.00"})

    # Tenta encerrar com saldo positivo
    res_encerrar = client.post(f"/contas/{conta_id}/encerrar")
    assert res_encerrar.status_code == 400
    assert "exige saldo zero" in res_encerrar.json()["detail"]


def test_regra_7_encerramento_conta_com_fatura_aberta(client, cliente_id):
    # Cria conta com saldo zero
    res_conta = client.post(
        "/contas",
        json={"cliente_id": cliente_id, "numero": "44444-4", "tipo": "corrente", "limite_credito": "0.00"},
    )
    conta_id = res_conta.json()["id"]

    # Cria cartão
    res_cartao = client.post(
        "/cartoes",
        json={"conta_id": conta_id, "numero": "1111-2222-3333-4444", "limite": "1000.00"},
    )
    cartao_id = res_cartao.json()["id"]

    # Cria fatura em aberto
    client.post(
        f"/cartoes/{cartao_id}/faturas",
        json={"mes_referencia": "2026-11", "valor": "150.00", "data_vencimento": "2026-12-10"},
    )

    # Tenta encerrar
    res_encerrar = client.post(f"/contas/{conta_id}/encerrar")
    assert res_encerrar.status_code == 400
    assert "nenhuma fatura aberta" in res_encerrar.json()["detail"]


def test_regra_7_encerramento_bem_sucedido_cancela_cartoes(client, cliente_id):
    # Cria conta com saldo zero
    res_conta = client.post(
        "/contas",
        json={"cliente_id": cliente_id, "numero": "55555-5", "tipo": "corrente", "limite_credito": "0.00"},
    )
    conta_id = res_conta.json()["id"]

    # Cria dois cartões
    c1 = client.post(
        "/cartoes",
        json={"conta_id": conta_id, "numero": "CAR-01", "limite": "1000.00"},
    ).json()["id"]
    c2 = client.post(
        "/cartoes",
        json={"conta_id": conta_id, "numero": "CAR-02", "limite": "2000.00"},
    ).json()["id"]

    # Encerra conta
    res_encerrar = client.post(f"/contas/{conta_id}/encerrar")
    assert res_encerrar.status_code == 200
    assert res_encerrar.json()["conta"]["estado"] == "encerrada"
    assert res_encerrar.json()["cartoes_cancelados"] == 2

    # Verifica se os cartões foram alterados para cancelado
    card1 = client.get(f"/cartoes/{c1}").json()
    card2 = client.get(f"/cartoes/{c2}").json()
    assert card1["estado"] == "cancelado"
    assert card2["estado"] == "cancelado"
