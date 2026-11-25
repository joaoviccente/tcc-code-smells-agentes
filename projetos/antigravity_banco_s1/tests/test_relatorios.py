from decimal import Decimal
import pytest
from tests.conftest import gerar_cpf_valido


def test_relatorio_maior_movimentacao(client):
    # Cliente 1
    cli1 = client.post(
        "/clientes", json={"nome": "Maior 1", "cpf": gerar_cpf_valido(921), "email": "m1@test.com", "categoria": "comum"}
    ).json()["id"]
    cta1 = client.post("/contas", json={"cliente_id": cli1, "numero": "CTA-M1", "limite_credito": "1000.00"}).json()["id"]
    client.post("/transacoes/deposito", json={"conta_id": cta1, "valor": "5000.00"})

    # Cliente 2
    cli2 = client.post(
        "/clientes", json={"nome": "Maior 2", "cpf": gerar_cpf_valido(922), "email": "m2@test.com", "categoria": "premium"}
    ).json()["id"]
    cta2 = client.post("/contas", json={"cliente_id": cli2, "numero": "CTA-M2", "limite_credito": "1000.00"}).json()["id"]
    client.post("/transacoes/deposito", json={"conta_id": cta2, "valor": "12000.00"})

    res = client.get("/relatorios/maior-movimentacao?limite=5")
    assert res.status_code == 200
    dados = res.json()["clientes"]
    assert len(dados) >= 2
    # Primeiro colocado deve ser o cliente 2 com 12.000
    assert dados[0]["cliente_id"] == cli2
    assert Decimal(dados[0]["total_movimentado"]) == Decimal("12000.00")
    # Segundo colocado deve ser o cliente 1 com 5.000
    assert dados[1]["cliente_id"] == cli1
    assert Decimal(dados[1]["total_movimentado"]) == Decimal("5000.00")


def test_relatorio_contas_saldo_negativo(client):
    cli = client.post(
        "/clientes", json={"nome": "Negativo Rel", "cpf": gerar_cpf_valido(931), "email": "nrel@test.com", "categoria": "comum"}
    ).json()["id"]
    cta = client.post("/contas", json={"cliente_id": cli, "numero": "CTA-NREL", "limite_credito": "500.00"}).json()["id"]
    client.post("/transacoes/saque", json={"conta_id": cta, "valor": "300.00"})

    res = client.get("/relatorios/contas-saldo-negativo")
    assert res.status_code == 200
    contas_neg = res.json()["contas"]
    assert any(c["conta_id"] == cta and Decimal(c["saldo"]) == Decimal("-300.00") for c in contas_neg)


def test_relatorio_receita_tarifas(client):
    # Cria conta Comum e gera tarifa mensal de 30.00
    cli = client.post(
        "/clientes", json={"nome": "Tarifa Rel", "cpf": gerar_cpf_valido(941), "email": "trel@test.com", "categoria": "comum"}
    ).json()["id"]
    cta = client.post("/contas", json={"cliente_id": cli, "numero": "CTA-TREL", "limite_credito": "500.00"}).json()["id"]
    client.post(f"/contas/{cta}/tarifas/cobrar-mensalidade")

    res = client.get("/relatorios/receita-tarifas")
    assert res.status_code == 200
    data = res.json()
    assert Decimal(data["total_geral"]) >= Decimal("30.00")
    cat_comum = next(c for c in data["categorias"] if c["categoria"] == "comum")
    assert Decimal(cat_comum["total_arrecadado"]) >= Decimal("30.00")
    assert cat_comum["quantidade_tarifas_cobradas"] >= 1
