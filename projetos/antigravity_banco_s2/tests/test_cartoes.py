from decimal import Decimal
from fastapi import status
from app.config import EstadoConta, EstadoCartao


def test_criar_cartao_sucesso(client, conta_comum):
    payload = {
        "conta_id": conta_comum.id,
        "numero": "5111111111111111",
        "limite": "2500.00",
    }
    response = client.post("/cartoes", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["numero"] == "5111111111111111"
    assert Decimal(data["limite"]) == Decimal("2500.00")
    assert data["estado"] == "ativo"


def test_criar_cartao_conta_bloqueada_falha(client, db, conta_comum):
    conta_comum.estado = EstadoConta.BLOQUEADA
    db.commit()

    payload = {
        "conta_id": conta_comum.id,
        "numero": "5111111111111111",
        "limite": "1000.00",
    }
    response = client.post("/cartoes", json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "bloqueada" in response.json()["detail"].lower()


def test_criar_cartao_numero_duplicado(client, cartao_comum):
    payload = {
        "conta_id": cartao_comum.conta_id,
        "numero": cartao_comum.numero,
        "limite": "1000.00",
    }
    response = client.post("/cartoes", json=payload)
    assert response.status_code == status.HTTP_409_CONFLICT


def test_listar_e_obter_cartao(client, cartao_comum):
    resp_lista = client.get(f"/cartoes?conta_id={cartao_comum.conta_id}")
    assert resp_lista.status_code == status.HTTP_200_OK
    assert len(resp_lista.json()) == 1

    resp_cartao = client.get(f"/cartoes/{cartao_comum.id}")
    assert resp_cartao.status_code == status.HTTP_200_OK
    assert resp_cartao.json()["numero"] == cartao_comum.numero


def test_atualizar_cartao(client, cartao_comum):
    payload = {
        "limite": "4500.00",
        "estado": "bloqueado"
    }
    response = client.put(f"/cartoes/{cartao_comum.id}", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert Decimal(data["limite"]) == Decimal("4500.00")
    assert data["estado"] == "bloqueado"


def test_deletar_cartao(client, cartao_comum):
    response = client.delete(f"/cartoes/{cartao_comum.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert client.get(f"/cartoes/{cartao_comum.id}").status_code == status.HTTP_404_NOT_FOUND
