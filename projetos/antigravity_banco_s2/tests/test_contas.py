from datetime import date
from decimal import Decimal
from fastapi import status
from app.models.cartao import Cartao
from app.models.fatura import Fatura
from app.config import EstadoConta, EstadoCartao, EstadoFatura


def test_criar_conta_sucesso(client, cliente_comum):
    payload = {
        "cliente_id": cliente_comum.id,
        "numero": "9999-9",
        "tipo": "corrente",
        "saldo": "100.00",
        "limite_credito": "500.00",
    }
    response = client.post("/contas", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["numero"] == "9999-9"
    assert data["cliente_id"] == cliente_comum.id
    assert Decimal(data["saldo"]) == Decimal("100.00")
    assert Decimal(data["limite_credito"]) == Decimal("500.00")
    assert data["estado"] == "ativa"


def test_criar_conta_cliente_inexistente(client):
    payload = {
        "cliente_id": 99999,
        "numero": "9999-9",
        "tipo": "corrente",
    }
    response = client.post("/contas", json=payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_criar_conta_numero_duplicado(client, conta_comum):
    payload = {
        "cliente_id": conta_comum.cliente_id,
        "numero": conta_comum.numero,
        "tipo": "corrente",
    }
    response = client.post("/contas", json=payload)
    assert response.status_code == status.HTTP_409_CONFLICT


def test_criar_conta_saldo_negativo_alem_do_limite(client, cliente_comum):
    payload = {
        "cliente_id": cliente_comum.id,
        "numero": "8888-8",
        "tipo": "corrente",
        "saldo": "-600.00",
        "limite_credito": "500.00",
    }
    response = client.post("/contas", json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_listar_e_obter_conta(client, conta_comum):
    resp_lista = client.get(f"/contas?cliente_id={conta_comum.cliente_id}")
    assert resp_lista.status_code == status.HTTP_200_OK
    assert len(resp_lista.json()) == 1

    resp_conta = client.get(f"/contas/{conta_comum.id}")
    assert resp_conta.status_code == status.HTTP_200_OK
    assert resp_conta.json()["numero"] == conta_comum.numero


def test_atualizar_conta(client, conta_comum):
    payload = {
        "limite_credito": "1500.00",
        "tipo": "poupanca"
    }
    response = client.put(f"/contas/{conta_comum.id}", json=payload)
    assert response.status_code == status.HTTP_200_OK
    assert Decimal(response.json()["limite_credito"]) == Decimal("1500.00")
    assert response.json()["tipo"] == "poupanca"


def test_regra_7_encerramento_conta_saldo_nao_zero_falha(client, conta_comum):
    # conta_comum tem saldo 2000.00
    response = client.post(f"/contas/{conta_comum.id}/encerrar")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "saldo deve ser exatamente R$ 0,00" in response.json()["detail"]


def test_regra_7_encerramento_conta_com_fatura_aberta_falha(client, db, conta_comum):
    # Zera saldo
    conta_comum.saldo = Decimal("0.00")
    db.commit()

    # Adiciona cartão e fatura aberta
    cartao = Cartao(
        conta_id=conta_comum.id,
        numero="5222222222222222",
        limite=Decimal("1000.00"),
        estado=EstadoCartao.ATIVO,
    )
    db.add(cartao)
    db.commit()
    db.refresh(cartao)

    fatura = Fatura(
        cartao_id=cartao.id,
        mes_referencia="2026-11",
        valor=Decimal("350.00"),
        valor_original=Decimal("350.00"),
        data_vencimento=date(2026, 11, 20),
        estado=EstadoFatura.ABERTA,
    )
    db.add(fatura)
    db.commit()

    # Tenta encerrar conta
    response = client.post(f"/contas/{conta_comum.id}/encerrar")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "fatura(s) aberta(s)" in response.json()["detail"]


def test_regra_7_encerramento_conta_sucesso_cancela_cartoes(client, db, conta_comum):
    # Zera saldo
    conta_comum.saldo = Decimal("0.00")
    db.commit()

    cartao = Cartao(
        conta_id=conta_comum.id,
        numero="5333333333333333",
        limite=Decimal("1000.00"),
        estado=EstadoCartao.ATIVO,
    )
    db.add(cartao)
    db.commit()
    db.refresh(cartao)

    response = client.post(f"/contas/{conta_comum.id}/encerrar")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["estado"] == "encerrada"

    # Confirma que a conta virou encerrada e o cartão virou cancelado
    db.refresh(conta_comum)
    db.refresh(cartao)
    assert conta_comum.estado == EstadoConta.ENCERRADA
    assert cartao.estado == EstadoCartao.CANCELADO
