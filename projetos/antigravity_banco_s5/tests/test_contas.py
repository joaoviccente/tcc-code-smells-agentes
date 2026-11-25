from decimal import Decimal
from fastapi import status


def test_criar_conta_sucesso(client):
    cli = client.post("/clientes", json={
        "nome": "João da Silva",
        "cpf": "52998224725",
        "email": "joao.conta@exemplo.com",
    }).json()

    res = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "1001-X",
        "tipo": "corrente",
        "limite_credito": 500.0,
    })
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert data["id"] is not None
    assert data["numero"] == "1001-X"
    assert Decimal(str(data["saldo"])) == Decimal("0.00")
    assert Decimal(str(data["limite_credito"])) == Decimal("500.00")
    assert data["estado"] == "ativa"


def test_criar_conta_numero_duplicado(client):
    cli = client.post("/clientes", json={
        "nome": "João da Silva",
        "cpf": "52998224725",
        "email": "joao.dup@exemplo.com",
    }).json()

    client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "9999",
        "tipo": "corrente",
    })

    res2 = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "9999",
        "tipo": "poupanca",
    })
    assert res2.status_code == status.HTTP_409_CONFLICT


def test_encerrar_conta_com_saldo_positivo_falha(client):
    cli = client.post("/clientes", json={
        "nome": "Cliente Saldo",
        "cpf": "52998224725",
        "email": "saldo@exemplo.com",
    }).json()

    conta = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "2001",
    }).json()

    # Deposita 100
    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 100.0})

    # Tenta encerrar com saldo != 0 -> deve falhar (Regra 7)
    res = client.post(f"/contas/{conta['id']}/encerrar")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "exige saldo zero" in res.json()["detail"]


def test_encerrar_conta_com_fatura_aberta_falha(client):
    cli = client.post("/clientes", json={
        "nome": "Cliente Fatura",
        "cpf": "52998224725",
        "email": "fatura.encerrar@exemplo.com",
    }).json()

    conta = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "2002",
    }).json()

    cartao = client.post("/cartoes", json={
        "conta_id": conta["id"],
        "numero": "4000123456789010",
        "limite": 1500.0,
    }).json()

    client.post("/faturas", json={
        "cartao_id": cartao["id"],
        "mes_referencia": "2026-11",
        "valor": 150.0,
        "data_vencimento": "2026-11-20",
    })

    # Tenta encerrar com fatura aberta -> deve falhar (Regra 7)
    res = client.post(f"/contas/{conta['id']}/encerrar")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "fatura(s) aberta(s)" in res.json()["detail"]


def test_encerrar_conta_sucesso_cancela_cartoes(client):
    cli = client.post("/clientes", json={
        "nome": "Cliente Cancelar",
        "cpf": "52998224725",
        "email": "cancela.cartoes@exemplo.com",
    }).json()

    conta = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "2003",
    }).json()

    cartao1 = client.post("/cartoes", json={
        "conta_id": conta["id"],
        "numero": "4000111122223333",
    }).json()
    cartao2 = client.post("/cartoes", json={
        "conta_id": conta["id"],
        "numero": "4000444455556666",
    }).json()

    res = client.post(f"/contas/{conta['id']}/encerrar")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["estado"] == "encerrada"

    # Verificar que os cartões foram cancelados (Regra 7)
    c1 = client.get(f"/cartoes/{cartao1['id']}").json()
    c2 = client.get(f"/cartoes/{cartao2['id']}").json()
    assert c1["estado"] == "cancelado"
    assert c2["estado"] == "cancelado"
