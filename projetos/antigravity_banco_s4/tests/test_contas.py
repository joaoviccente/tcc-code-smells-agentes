from decimal import Decimal
from tests.conftest import gerar_cpf


def test_criar_conta_sucesso(client):
    cli = client.post("/clientes", json={"nome": "Titular", "cpf": gerar_cpf(201), "email": "titular@ex.com", "categoria": "comum"}).json()

    res = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "12345-6",
        "tipo": "corrente",
        "limite_de_credito": 500.0,
        "saldo_inicial": 100.0,
    })
    assert res.status_code == 201
    data = res.json()
    assert data["numero"] == "12345-6"
    assert data["tipo"] == "corrente"
    assert float(data["saldo"]) == 100.0
    assert float(data["limite_de_credito"]) == 500.0
    assert data["estado"] == "ativa"


def test_criar_conta_cliente_bloqueado(client):
    cli = client.post("/clientes", json={"nome": "Bloqueado", "cpf": gerar_cpf(202), "email": "bloq@ex.com", "categoria": "comum"}).json()
    client.put(f"/clientes/{cli['id']}", json={"situacao": "bloqueado"})

    res = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "99999-9",
        "tipo": "corrente",
    })
    assert res.status_code == 400
    assert "cliente bloqueado" in res.json()["detail"].lower()


def test_criar_conta_numero_duplicado(client):
    cli = client.post("/clientes", json={"nome": "User 1", "cpf": gerar_cpf(203), "email": "u1@ex.com", "categoria": "comum"}).json()
    client.post("/contas", json={"cliente_id": cli["id"], "numero": "11111-1", "tipo": "corrente"})

    res = client.post("/contas", json={"cliente_id": cli["id"], "numero": "11111-1", "tipo": "poupanca"})
    assert res.status_code == 409
    assert "já existe" in res.json()["detail"].lower()


def test_regra_7_encerramento_conta_saldo_positivo(client):
    cli = client.post("/clientes", json={"nome": "Regra 7 Positivo", "cpf": gerar_cpf(204), "email": "r7pos@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "20001-1", "tipo": "corrente", "saldo_inicial": 50.0}).json()

    res = client.delete(f"/contas/{conta['id']}")
    assert res.status_code == 400
    assert "deve ser exatamente zero" in res.json()["detail"].lower()


def test_regra_7_encerramento_conta_com_fatura_aberta(client):
    cli = client.post("/clientes", json={"nome": "Regra 7 Fatura", "cpf": gerar_cpf(205), "email": "r7fat@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "20002-2", "tipo": "corrente", "saldo_inicial": 0.0}).json()
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "4000111122223333", "limite": 1000.0}).json()
    
    # Cria fatura aberta no cartão
    client.post("/faturas", json={
        "cartao_id": cartao["id"],
        "mes_referencia": "2026-11",
        "valor": 150.0,
        "data_vencimento": "2026-11-20",
    })

    # Tenta encerrar a conta com fatura aberta
    res = client.post(f"/contas/{conta['id']}/encerrar")
    assert res.status_code == 400
    assert "fatura(s) pendente(s) ou aberta(s)" in res.json()["detail"].lower()


def test_regra_7_encerramento_sucesso_cancela_cartoes(client):
    cli = client.post("/clientes", json={"nome": "Regra 7 Sucesso", "cpf": gerar_cpf(206), "email": "r7suc@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "20003-3", "tipo": "corrente", "saldo_inicial": 0.0}).json()
    cartao1 = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "4000444455556666", "limite": 1000.0}).json()
    cartao2 = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "4000777788889999", "limite": 2000.0}).json()

    # Encerra a conta
    res = client.post(f"/contas/{conta['id']}/encerrar")
    assert res.status_code == 200
    data = res.json()
    assert data["estado"] == "encerrada"
    assert cartao1["id"] in data["cartoes_cancelados_ids"]
    assert cartao2["id"] in data["cartoes_cancelados_ids"]

    # Verifica se os cartões foram efetivamente cancelados
    c1 = client.get(f"/cartoes/{cartao1['id']}").json()
    c2 = client.get(f"/cartoes/{cartao2['id']}").json()
    assert c1["estado"] == "cancelado"
    assert c2["estado"] == "cancelado"
