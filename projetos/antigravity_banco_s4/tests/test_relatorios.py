from datetime import datetime, timedelta
from tests.conftest import gerar_cpf
from app.models.conta import Conta


def test_relatorio_maior_movimentacao(client):
    # Cliente 1: movimenta 1000
    cli1 = client.post("/clientes", json={"nome": "Cli Mov 1", "cpf": gerar_cpf(701), "email": "m1@ex.com", "categoria": "comum"}).json()
    conta1 = client.post("/contas", json={"cliente_id": cli1["id"], "numero": "70001-1", "tipo": "corrente"}).json()
    client.post("/transacoes/deposito", json={"conta_id": conta1["id"], "valor": 1000.0})

    # Cliente 2: movimenta 3000
    cli2 = client.post("/clientes", json={"nome": "Cli Mov 2", "cpf": gerar_cpf(702), "email": "m2@ex.com", "categoria": "premium"}).json()
    conta2 = client.post("/contas", json={"cliente_id": cli2["id"], "numero": "70002-2", "tipo": "corrente"}).json()
    client.post("/transacoes/deposito", json={"conta_id": conta2["id"], "valor": 3000.0})

    res = client.get("/relatorios/clientes-maior-movimentacao")
    assert res.status_code == 200
    data = res.json()
    assert data["total_clientes_listados"] >= 2
    # Primeiro colocado deve ser o Cliente 2
    assert data["clientes"][0]["cliente_id"] == cli2["id"]
    assert float(data["clientes"][0]["total_movimentado"]) == 3000.0
    # Segundo colocado deve ser o Cliente 1
    assert data["clientes"][1]["cliente_id"] == cli1["id"]
    assert float(data["clientes"][1]["total_movimentado"]) == 1000.0


def test_relatorio_contas_saldo_negativo(client):
    cli = client.post("/clientes", json={"nome": "Neg User", "cpf": gerar_cpf(703), "email": "neg@ex.com", "categoria": "comum"}).json()
    # Cria conta com saldo 0 e limite 500
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "70003-3", "tipo": "corrente", "limite_de_credito": 500.0}).json()
    # Saque de 250 -> saldo fica -250
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 250.0})

    res = client.get("/relatorios/contas-saldo-negativo")
    assert res.status_code == 200
    data = res.json()
    assert data["total_contas_negativas"] >= 1
    conta_neg = next(c for c in data["contas"] if c["conta_id"] == conta["id"])
    assert float(conta_neg["saldo"]) == -250.0


def test_relatorio_receita_tarifas_por_categoria(client):
    # Cria contas de categorias distintas e cobra mensalidades
    cli_c = client.post("/clientes", json={"nome": "Cli C", "cpf": gerar_cpf(704), "email": "c@ex.com", "categoria": "comum"}).json()
    conta_c = client.post("/contas", json={"cliente_id": cli_c["id"], "numero": "70004-1", "tipo": "corrente", "saldo_inicial": 100.0}).json()

    cli_e = client.post("/clientes", json={"nome": "Cli E", "cpf": gerar_cpf(705), "email": "e@ex.com", "categoria": "empresarial"}).json()
    conta_e = client.post("/contas", json={"cliente_id": cli_e["id"], "numero": "70004-2", "tipo": "corrente", "saldo_inicial": 200.0}).json()

    # Cobrança de mensalidade: Comum R$ 30, Empresarial R$ 120 -> Total 150
    client.post("/tarifas/cobrar-mensalidades")

    res = client.get("/relatorios/receita-tarifas-por-categoria")
    assert res.status_code == 200
    data = res.json()
    assert float(data["receita_total"]) == 150.0
    assert data["total_tarifas_cobradas"] == 2

    cat_comum = next(item for item in data["receita_por_categoria"] if item["categoria"] == "comum")
    assert float(cat_comum["valor_total"]) == 30.0

    cat_emp = next(item for item in data["receita_por_categoria"] if item["categoria"] == "empresarial")
    assert float(cat_emp["valor_total"]) == 120.0


def test_regra_6_bloqueio_apos_30_dias_negativo(client, db_session):
    """
    Regra 6: Conta com saldo negativo por mais de 30 dias bloqueia o cliente e todos os seus cartões.
    """
    cli = client.post("/clientes", json={"nome": "Inadimplente 30d", "cpf": gerar_cpf(706), "email": "inad@ex.com", "categoria": "comum"}).json()
    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "70006-6", "tipo": "corrente", "saldo_inicial": 0.0, "limite_de_credito": 1000.0}).json()
    cartao1 = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "7000111122223333", "limite": 1500.0}).json()
    cartao2 = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "7000444455556666", "limite": 1500.0}).json()

    # Saque que torna o saldo negativo (-200)
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 200.0})

    # Simular que a conta está negativa há 31 dias
    c_db = db_session.query(Conta).filter(Conta.id == conta["id"]).first()
    c_db.data_saldo_negativo_inicio = datetime.utcnow() - timedelta(days=31)
    db_session.commit()

    # Executa a rotina de verificação de contas negativas
    res_rotina = client.post("/rotinas/processar-contas-negativas")
    assert res_rotina.status_code == 200
    rotina_data = res_rotina.json()
    assert cli["id"] in rotina_data["clientes_bloqueados"]

    # Verifica se o cliente foi bloqueado
    cli_check = client.get(f"/clientes/{cli['id']}").json()
    assert cli_check["situacao"] == "bloqueado"

    # Verifica se todos os cartões foram bloqueados
    c1_check = client.get(f"/cartoes/{cartao1['id']}").json()
    c2_check = client.get(f"/cartoes/{cartao2['id']}").json()
    assert c1_check["estado"] == "bloqueado"
    assert c2_check["estado"] == "bloqueado"

    # Tentativa de nova operação deve ser negada pois o cliente está bloqueado (Regra 1)
    res_saque = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 50.0})
    assert res_saque.status_code == 400
    assert "titular da conta está bloqueado" in res_saque.json()["detail"].lower()
