from fastapi import status


def test_crud_cartao(client):
    cli = client.post("/clientes", json={
        "nome": "Cliente Cartao",
        "cpf": "52998224725",
        "email": "cartao@exemplo.com",
    }).json()

    conta = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "3001",
    }).json()

    # Criar cartão
    res = client.post("/cartoes", json={
        "conta_id": conta["id"],
        "numero": "5500123412341234",
        "limite": 2500.0,
    })
    assert res.status_code == status.HTTP_201_CREATED
    cartao = res.json()
    assert cartao["numero"] == "5500123412341234"
    assert cartao["estado"] == "ativo"

    # Duplicidade de cartão
    res_dup = client.post("/cartoes", json={
        "conta_id": conta["id"],
        "numero": "5500123412341234",
        "limite": 1000.0,
    })
    assert res_dup.status_code == status.HTTP_409_CONFLICT

    # Atualizar limite
    res_up = client.put(f"/cartoes/{cartao['id']}", json={"limite": 3500.0})
    assert res_up.status_code == status.HTTP_200_OK
    assert float(res_up.json()["limite"]) == 3500.0

    # Cancelar cartão
    res_del = client.delete(f"/cartoes/{cartao['id']}")
    assert res_del.status_code == status.HTTP_200_OK
    assert res_del.json()["estado"] == "cancelado"
