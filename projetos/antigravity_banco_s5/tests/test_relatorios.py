from decimal import Decimal
from fastapi import status


def test_relatorios_completos(client):
    # Setup de clientes e contas
    cli1 = client.post("/clientes", json={
        "nome": "Cliente Movimenta Muito",
        "cpf": "52998224725",
        "email": "movimenta@exemplo.com",
        "categoria": "comum",
    }).json()

    cli2 = client.post("/clientes", json={
        "nome": "Cliente Movimenta Pouco",
        "cpf": "11144477735",
        "email": "pouco@exemplo.com",
        "categoria": "premium",
    }).json()

    c1 = client.post("/contas", json={"cliente_id": cli1["id"], "numero": "8801", "limite_credito": 1000.0}).json()
    c2 = client.post("/contas", json={"cliente_id": cli2["id"], "numero": "8802"}).json()

    # Movimentações
    # cli1 faz depósito de 1000 e saque de 300 -> total movimentado = 1300
    client.post("/transacoes/deposito", json={"conta_id": c1["id"], "valor": 1000.0})
    client.post("/transacoes/saque", json={"conta_id": c1["id"], "valor": 300.0})

    # cli2 faz depósito de 100 -> total movimentado = 100
    client.post("/transacoes/deposito", json={"conta_id": c2["id"], "valor": 100.0})

    # 1. Relatório de Clientes com Maior Movimentação
    res_mov = client.get("/relatorios/clientes-maior-movimentacao")
    assert res_mov.status_code == status.HTTP_200_OK
    itens_mov = res_mov.json()
    assert len(itens_mov) >= 2
    assert itens_mov[0]["cliente_id"] == cli1["id"]
    assert Decimal(str(itens_mov[0]["total_movimentado"])) == Decimal("1300.00")

    # Deixar uma conta com saldo negativo
    c3 = client.post("/contas", json={"cliente_id": cli1["id"], "numero": "8803", "limite_credito": 500.0}).json()
    client.post("/transacoes/saque", json={"conta_id": c3["id"], "valor": 250.0})  # saldo fica -250

    # 2. Relatório de Contas com Saldo Negativo
    res_neg = client.get("/relatorios/contas-saldo-negativo")
    assert res_neg.status_code == status.HTTP_200_OK
    itens_neg = res_neg.json()
    assert len(itens_neg) >= 1
    conta_neg = next((item for item in itens_neg if item["conta_id"] == c3["id"]), None)
    assert conta_neg is not None
    assert Decimal(str(conta_neg["saldo"])) == Decimal("-250.00")

    # 3. Relatório de Receita de Tarifas por Categoria
    # Cobrar mensalidade de conta Comum (R$ 30,00)
    client.post(f"/contas/{c1['id']}/cobrar-mensalidade")

    res_rec = client.get("/relatorios/receita-tarifas-categoria")
    assert res_rec.status_code == status.HTTP_200_OK
    itens_rec = res_rec.json()
    assert len(itens_rec) == 3  # comum, premium, empresarial
    comum_rec = next((item for item in itens_rec if item["categoria"] == "comum"), None)
    assert comum_rec is not None
    assert Decimal(str(comum_rec["total_receita"])) >= Decimal("30.00")
