from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def banco(tmp_path, monkeypatch):
    instante = [datetime(2026, 1, 15, 12, tzinfo=UTC)]
    monkeypatch.setattr(main, "agora", lambda: instante[0])
    with TestClient(main.criar_app(tmp_path / "banco.sqlite3")) as api:
        yield api, instante


def criar(api, rota, **dados):
    resposta = api.post(rota, json=dados)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def cliente(api, categoria="comum", cpf="52998224725"):
    return criar(api, "/clientes", nome="Cliente", cpf=cpf, email="cliente@example.com",
                 categoria=categoria)


def conta(api, cliente_id, numero="001", limite="0"):
    return criar(api, "/contas", cliente_id=cliente_id, numero=numero, tipo="corrente",
                 limite_credito=limite)


def saldo(api, conta_id):
    return api.get(f"/contas/{conta_id}").json()["saldo"]


@pytest.mark.parametrize("categoria,saque,transferencia,mensal", [
    ("comum", 1000, 5000, "30.00"),
    ("premium", 5000, 50000, "0.00"),
    ("empresarial", 20000, 200000, "120.00"),
])
def test_limites_e_mensalidade(banco, categoria, saque, transferencia, mensal):
    api, _ = banco
    titular = cliente(api, categoria)
    origem = conta(api, titular)
    destino = conta(api, titular, "002")
    criar(api, f"/contas/{origem}/depositos", valor="300000.00")
    criar(api, f"/contas/{destino}/depositos", valor="500.00")
    criar(api, f"/contas/{origem}/saques", valor=saque)
    assert api.post(f"/contas/{destino}/saques", json={"valor": "0.01"}).status_code == 409
    criar(api, f"/contas/{origem}/transferencias", valor=transferencia, destino_id=destino)
    assert api.post(f"/contas/{origem}/transferencias",
                    json={"valor": transferencia + 1, "destino_id": destino}).status_code == 409
    tarifas = api.get(f"/contas/{origem}/tarifas").json()
    assert [(t["tipo"], t["valor"]) for t in tarifas] == [
        ("mensal", mensal), ("transferencia", "0.00")
    ]


def test_franquia_estorno_e_receita(banco):
    api, instante = banco
    titular = cliente(api)
    origem = conta(api, titular)
    destino = conta(api, cliente(api, "premium", "11144477735"), "002")
    criar(api, f"/contas/{origem}/depositos", valor=100)
    for _ in range(3):
        criar(api, f"/contas/{origem}/transferencias", valor=1, destino_id=destino)
    transacao = criar(api, f"/contas/{origem}/transferencias", valor=1, destino_id=destino)
    assert saldo(api, origem) == "65.00"
    assert saldo(api, destino) == "4.00"
    receita = api.get("/relatorios/receita-tarifas?inicio=2026-01-15&fim=2026-01-15")
    assert receita.json()[0] == {"categoria": "comum", "total": "31.00"}
    instante[0] += timedelta(hours=24)
    criar(api, f"/transacoes/{transacao}/estorno")
    assert saldo(api, origem) == "67.00"
    assert saldo(api, destino) == "3.00"
    assert api.post(f"/transacoes/{transacao}/estorno").status_code == 409
    extrato = api.get(f"/contas/{destino}/extrato").json()
    assert [(t["tipo"], t["estado"]) for t in extrato[-2:]] == [
        ("transferencia", "estornada"), ("estorno", "efetivada")
    ]
    assert api.get("/relatorios/movimentacao?inicio=2026-01-15&fim=2026-01-16").json()[0][
        "total"
    ] == "103.00"


def test_credito_e_bloqueio_por_saldo(banco):
    api, instante = banco
    titular = cliente(api, "premium")
    origem = conta(api, titular, limite="100.00")
    outra = conta(api, titular, "002")
    cartao = criar(api, "/cartoes", conta_id=outra, numero="123", limite=100)
    saque = criar(api, f"/contas/{origem}/saques", valor=100)
    assert api.post(f"/contas/{origem}/saques", json={"valor": "0.01"}).status_code == 409
    instante[0] += timedelta(days=30)
    assert api.get(f"/clientes/{titular}").json()["situacao"] == "ativo"
    assert api.post(f"/transacoes/{saque}/estorno").status_code == 409
    instante[0] += timedelta(seconds=1)
    assert api.get(f"/clientes/{titular}").json()["situacao"] == "bloqueado"
    assert api.get(f"/cartoes/{cartao}").json()["estado"] == "bloqueado"
    assert api.get("/relatorios/saldos-negativos").json()[0]["saldo"] == "-100.00"
    assert api.delete(f"/contas/{origem}").status_code == 409


@pytest.mark.parametrize("categoria,juros", [
    ("comum", "26.40"), ("premium", "16.50"), ("empresarial", "9.90"),
])
def test_fatura_pagamento_e_encerramento(banco, categoria, juros):
    api, instante = banco
    origem = conta(api, cliente(api, categoria))
    cartao = criar(api, "/cartoes", conta_id=origem, numero="123", limite=1000)
    fatura = criar(api, f"/cartoes/{cartao}/faturas", mes_referencia="2026-01",
                   vencimento="2026-01-15", valor=900, estado="aberta")
    assert api.delete(f"/contas/{origem}").status_code == 409
    instante[0] += timedelta(days=10)
    assert api.get(f"/cartoes/{cartao}").json()["estado"] == "ativo"
    instante[0] += timedelta(days=1)
    assert api.get(f"/cartoes/{cartao}").json()["estado"] == "bloqueado"
    atrasada = api.get(f"/cartoes/{cartao}/faturas").json()[0]
    assert (atrasada["estado"], atrasada["juros"]) == ("atrasada", juros)
    assert api.post(f"/faturas/{fatura}/pagamento").json()["estado"] == "paga"
    assert api.post(f"/faturas/{fatura}/pagamento").status_code == 409
    assert api.delete(f"/contas/{origem}").status_code == 204
    assert api.get(f"/cartoes/{cartao}").json()["estado"] == "cancelado"


def test_validacao_e_crud(banco):
    api, _ = banco
    assert api.post("/clientes", json={"cpf": "123"}).status_code == 422
    titular = cliente(api)
    assert api.post("/clientes", json={
        "nome": "Duplicado", "cpf": "529.982.247-25", "email": "a@example.com",
        "categoria": "comum",
    }).status_code == 409
    origem = conta(api, titular)
    assert api.post(f"/contas/{origem}/depositos", json={"valor": "1.001"}).status_code == 422
    assert api.get("/contas/999").status_code == 404
    assert api.put(f"/contas/{origem}", json={"tipo": "poupanca", "estado": "bloqueada"}).status_code == 200
    assert api.post(f"/contas/{origem}/saques", json={"valor": 1}).status_code == 409
    assert api.delete(f"/clientes/{titular}").status_code == 409

def test_mensalidades_de_competencias_sem_acesso(banco):
    api, instante = banco
    origem = conta(api, cliente(api))
    instante[0] = instante[0].replace(month=3)
    criar(api, f"/contas/{origem}/depositos", valor=100)
    tarifas = api.get(f"/contas/{origem}/tarifas").json()
    assert [(t["competencia"], t["estado"]) for t in tarifas] == [
        ("2026-01", "cobrada"), ("2026-02", "cobrada"), ("2026-03", "cobrada")
    ]
    assert saldo(api, origem) == "10.00"
