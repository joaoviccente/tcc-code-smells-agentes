from tests.conftest import gerar_cpf


def test_criar_cartao_sucesso(client):
    cli = client.post("/clientes", json={"nome": "Cartao User", "cpf": gerar_cpf(301), "email": "cuser@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "30001-1", "tipo": "corrente"}).json()

    res = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "5555666677778888", "limite": 3000.0})
    assert res.status_code == 201
    data = res.json()
    assert data["numero"] == "5555666677778888"
    assert float(data["limite"]) == 3000.0
    assert data["estado"] == "ativo"


def test_criar_cartao_conta_bloqueada(client):
    cli = client.post("/clientes", json={"nome": "Cartao Bloq", "cpf": gerar_cpf(302), "email": "cbloq@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "30002-2", "tipo": "corrente"}).json()
    client.put(f"/contas/{conta['id']}", json={"estado": "bloqueada"})

    res = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "5555666677770000", "limite": 1000.0})
    assert res.status_code == 400
    assert "não é possível emitir cartão" in res.json()["detail"].lower()


def test_cancelar_cartao(client):
    cli = client.post("/clientes", json={"nome": "Cartao Cancel", "cpf": gerar_cpf(303), "email": "ccanc@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "30003-3", "tipo": "corrente"}).json()
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "5555666677771111", "limite": 1000.0}).json()

    res = client.delete(f"/cartoes/{cartao['id']}")
    assert res.status_code == 200
    assert res.json()["estado"] == "cancelado"
