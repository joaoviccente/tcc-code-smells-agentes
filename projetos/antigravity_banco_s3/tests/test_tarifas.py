def test_criar_e_listar_tarifas(client):
    cli = client.post(
        "/clientes",
        json={"nome": "Cli Tarifa", "cpf": "12345678909", "email": "tarifa_crud@example.com", "categoria": "comum"},
    ).json()

    conta = client.post(
        "/contas",
        json={"cliente_id": cli["id"], "numero": "C-TAR-01", "saldo_inicial": 200.0, "limite_credito": 0.0},
    ).json()

    # Cria tarifa avulsa
    res_cria = client.post(
        "/tarifas",
        json={
            "conta_id": conta["id"],
            "tipo": "saque",
            "valor": 6.50,
            "estado": "pendente",
        },
    )
    assert res_cria.status_code == 201
    tar = res_cria.json()
    assert tar["tipo"] == "saque"
    assert float(tar["valor"]) == 6.50
    assert tar["estado"] == "pendente"

    # Listar tarifas por endpoint /tarifas/conta/{id}
    res_list1 = client.get(f"/tarifas/conta/{conta['id']}")
    assert res_list1.status_code == 200
    assert len(res_list1.json()) == 1

    # Listar tarifas por endpoint /contas/{id}/tarifas
    res_list2 = client.get(f"/contas/{conta['id']}/tarifas")
    assert res_list2.status_code == 200
    assert len(res_list2.json()) == 1
