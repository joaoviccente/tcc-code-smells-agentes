import pytest
from tests.conftest import gerar_cpf_valido


@pytest.fixture
def clientes_e_contas(client):
    cpf1 = gerar_cpf_valido(701)
    cpf2 = gerar_cpf_valido(702)

    cli1 = client.post(
        "/clientes", json={"nome": "Cli 1", "cpf": cpf1, "email": "cli1@transf.com", "categoria": "comum"}
    ).json()["id"]
    cli2 = client.post(
        "/clientes", json={"nome": "Cli 2", "cpf": cpf2, "email": "cli2@transf.com", "categoria": "comum"}
    ).json()["id"]

    cta1 = client.post(
        "/contas", json={"cliente_id": cli1, "numero": "CTA-T1", "tipo": "corrente", "limite_credito": "1000.00"}
    ).json()["id"]
    cta2 = client.post(
        "/contas", json={"cliente_id": cli2, "numero": "CTA-T2", "tipo": "corrente", "limite_credito": "500.00"}
    ).json()["id"]

    return {"cli1": cli1, "cli2": cli2, "cta1": cta1, "cta2": cta2}


def test_deposito_e_extrato(client, clientes_e_contas):
    cta1 = clientes_e_contas["cta1"]
    res_dep = client.post(
        "/transacoes/deposito",
        json={"conta_id": cta1, "valor": "500.00", "descricao": "Depósito em dinheiro"},
    )
    assert res_dep.status_code == 201
    assert res_dep.json()["tipo"] == "deposito"
    assert res_dep.json()["valor"] == "500.00"

    # Checa extrato
    res_ext = client.get(f"/contas/{cta1}/extrato")
    assert res_ext.status_code == 200
    ext = res_ext.json()
    assert ext["saldo_atual"] == "500.00"
    assert ext["limite_credito"] == "1000.00"
    assert ext["saldo_disponivel"] == "1500.00"
    assert len(ext["transacoes"]) == 1


def test_saque_com_sucesso(client, clientes_e_contas):
    cta1 = clientes_e_contas["cta1"]
    # Depósito inicial
    client.post("/transacoes/deposito", json={"conta_id": cta1, "valor": "500.00"})

    # Saque de 200
    res_saque = client.post(
        "/transacoes/saque",
        json={"conta_id": cta1, "valor": "200.00", "descricao": "Saque terminal"},
    )
    assert res_saque.status_code == 201
    assert res_saque.json()["tipo"] == "saque"
    assert res_saque.json()["valor"] == "200.00"

    ext = client.get(f"/contas/{cta1}/extrato").json()
    assert ext["saldo_atual"] == "300.00"


def test_transferencia_entre_contas(client, clientes_e_contas):
    cta1 = clientes_e_contas["cta1"]
    cta2 = clientes_e_contas["cta2"]

    client.post("/transacoes/deposito", json={"conta_id": cta1, "valor": "1000.00"})

    res_transf = client.post(
        "/transacoes/transferencia",
        json={
            "conta_origem_id": cta1,
            "conta_destino_id": cta2,
            "valor": "400.00",
            "descricao": "Pagamento de serviço",
        },
    )
    assert res_transf.status_code == 201
    assert res_transf.json()["tipo"] == "transferencia"
    assert res_transf.json()["valor"] == "400.00"

    ext1 = client.get(f"/contas/{cta1}/extrato").json()
    ext2 = client.get(f"/contas/{cta2}/extrato").json()

    assert ext1["saldo_atual"] == "600.00"
    assert ext2["saldo_atual"] == "400.00"
