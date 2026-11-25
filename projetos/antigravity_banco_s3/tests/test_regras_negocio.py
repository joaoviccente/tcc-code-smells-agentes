from datetime import datetime, timezone, timedelta
from decimal import Decimal
from app.models.conta import Conta


def test_regras_limites_empresarial(client):
    # Empresarial: limite diário de saque R$ 20.000,00; limite por transferência R$ 200.000,00
    cli = client.post(
        "/clientes",
        json={
            "nome": "Empresa Alfa Ltda",
            "cpf": "12345678909",
            "email": "alfa@empresa.com",
            "categoria": "empresarial",
        },
    ).json()

    c1 = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "EMP-01",
            "tipo": "corrente",
            "saldo_inicial": 300000.0,
            "limite_credito": 50000.0,
        },
    ).json()

    c2 = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "EMP-02",
            "tipo": "corrente",
            "saldo_inicial": 1000.0,
            "limite_credito": 0.0,
        },
    ).json()

    # Saque de 20.000,00 deve passar
    res_saque1 = client.post(
        "/transacoes/saque", json={"conta_id": c1["id"], "valor": 20000.0}
    )
    assert res_saque1.status_code == 201

    # Novo saque no mesmo dia de 1 real deve falhar (limite diário de 20.000,00 atingido)
    res_saque2 = client.post(
        "/transacoes/saque", json={"conta_id": c1["id"], "valor": 1.0}
    )
    assert res_saque2.status_code == 400

    # Transferência de 200.000,00 deve passar
    res_transf1 = client.post(
        "/transacoes/transferencia",
        json={
            "conta_origem_id": c1["id"],
            "conta_destino_id": c2["id"],
            "valor": 200000.0,
        },
    )
    assert res_transf1.status_code == 201

    # Transferência de 200.000,01 deve falhar (excede o limite de transferência)
    res_transf2 = client.post(
        "/transacoes/transferencia",
        json={
            "conta_origem_id": c1["id"],
            "conta_destino_id": c2["id"],
            "valor": 200000.01,
        },
    )
    assert res_transf2.status_code == 400


def test_regra_saldo_negativo_mais_30_dias(client, db_session):
    # Regra 6: Conta com saldo negativo por mais de 30 dias bloqueia o cliente e todos os seus cartões.
    cli = client.post(
        "/clientes",
        json={
            "nome": "Cliente Inadimplente",
            "cpf": "12345678909",
            "email": "inadimplente@example.com",
            "categoria": "comum",
        },
    ).json()

    conta = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "NEG-30D",
            "tipo": "corrente",
            "saldo_inicial": 0.0,
            "limite_credito": 1000.0,
        },
    ).json()

    cartao = client.post(
        "/cartoes",
        json={"conta_id": conta["id"], "numero": "CARD-NEG-1", "limite": 500.0},
    ).json()
    assert cartao["estado"] == "ativo"

    # Faz saque deixando saldo negativo
    res_saque = client.post(
        "/transacoes/saque", json={"conta_id": conta["id"], "valor": 200.0}
    )
    assert res_saque.status_code == 201

    # Simula passagem de 35 dias no saldo negativo no banco de dados
    conta_db = db_session.query(Conta).filter(Conta.id == conta["id"]).first()
    conta_db.saldo_negativo_desde = datetime.now(timezone.utc) - timedelta(days=35)
    db_session.commit()

    # Executa a rotina de verificação de saldo negativo > 30 dias
    res_rotina = client.post("/rotinas/processar-saldo-negativo")
    assert res_rotina.status_code == 200
    assert res_rotina.json()["clientes_bloqueados"] == 1

    # Verifica cliente bloqueado
    cli_updated = client.get(f"/clientes/{cli['id']}").json()
    assert cli_updated["situacao"] == "bloqueado"

    # Verifica cartão bloqueado
    cartao_updated = client.get(f"/cartoes/{cartao['id']}").json()
    assert cartao_updated["estado"] == "bloqueado"


def test_relatorios(client):
    # Cria clientes e contas
    c_comum = client.post(
        "/clientes",
        json={
            "nome": "Cliente Relatorio 1",
            "cpf": "12345678909",
            "email": "rel1@example.com",
            "categoria": "comum",
        },
    ).json()

    c_emp = client.post(
        "/clientes",
        json={
            "nome": "Cliente Relatorio 2",
            "cpf": "98765432100",
            "email": "rel2@example.com",
            "categoria": "empresarial",
        },
    ).json()

    conta1 = client.post(
        "/contas",
        json={
            "cliente_id": c_comum["id"],
            "numero": "REL-C1",
            "tipo": "corrente",
            "saldo_inicial": 5000.0,
            "limite_credito": 1000.0,
        },
    ).json()

    conta2 = client.post(
        "/contas",
        json={
            "cliente_id": c_emp["id"],
            "numero": "REL-C2",
            "tipo": "corrente",
            "saldo_inicial": 10000.0,
            "limite_credito": 2000.0,
        },
    ).json()

    # Movimentações
    client.post(
        "/transacoes/saque", json={"conta_id": conta1["id"], "valor": 500.0}
    )
    client.post(
        "/transacoes/deposito", json={"conta_id": conta2["id"], "valor": 4000.0}
    )

    # 1. Relatório de movimentação
    res_mov = client.get("/relatorios/clientes-maior-movimentacao")
    assert res_mov.status_code == 200
    mov_data = res_mov.json()
    assert len(mov_data) >= 2
    # c_emp deve estar em primeiro lugar (movimentou saldo inicial 10000 + deposito 4000 = 14000)
    assert mov_data[0]["cliente_id"] == c_emp["id"]

    # 2. Relatório de saldo negativo
    # Deixar conta1 com saldo negativo
    client.post(
        "/transacoes/saque", json={"conta_id": conta1["id"], "valor": 500.0}
    )
    # Total sacado hoje: 500 + 500 = 1000 (limite Comum atingido). Saldo = 4000
    res_neg = client.get("/relatorios/contas-saldo-negativo")
    assert res_neg.status_code == 200

    # 3. Relatório de receita de tarifas por categoria
    # Cobra tarifa mensal na conta2 (Empresarial: R$ 120,00)
    client.post(f"/contas/{conta2['id']}/tarifas/cobrar-mensalidade")

    res_rec = client.get("/relatorios/receita-tarifas-categoria")
    assert res_rec.status_code == 200
    rec_data = {r["categoria"]: float(r["total_arrecadado"]) for r in res_rec.json()}
    assert rec_data["empresarial"] == 120.0
