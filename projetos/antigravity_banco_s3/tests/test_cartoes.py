def test_crud_cartoes(client):
    cli = client.post(
        "/clientes",
        json={"nome": "Titular Cartao", "cpf": "12345678909", "email": "cart@example.com", "categoria": "comum"},
    ).json()

    conta = client.post(
        "/contas",
        json={"cliente_id": cli["id"], "numero": "C-CARD-01", "saldo_inicial": 500.0, "limite_credito": 0.0},
    ).json()

    # 1. Cria cartão
    res_cria = client.post(
        "/cartoes",
        json={"conta_id": conta["id"], "numero": "5555-4444-3333-2222", "limite": 2500.0},
    )
    assert res_cria.status_code == 201
    cartao = res_cria.json()
    assert cartao["numero"] == "5555-4444-3333-2222"
    assert float(cartao["limite"]) == 2500.0
    assert cartao["estado"] == "ativo"

    # 2. Listar cartões
    res_list = client.get(f"/cartoes?conta_id={conta['id']}")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # 3. Obter por ID
    res_get = client.get(f"/cartoes/{cartao['id']}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == cartao["id"]

    # 4. Atualizar cartão
    res_up = client.put(f"/cartoes/{cartao['id']}", json={"limite": 3000.0, "estado": "bloqueado"})
    assert res_up.status_code == 200
    assert float(res_up.json()["limite"]) == 3000.0
    assert res_up.json()["estado"] == "bloqueado"

    # 5. Deletar cartão
    res_del = client.delete(f"/cartoes/{cartao['id']}")
    assert res_del.status_code == 204

    # Verifica que não existe mais
    res_get_404 = client.get(f"/cartoes/{cartao['id']}")
    assert res_get_404.status_code == 404
