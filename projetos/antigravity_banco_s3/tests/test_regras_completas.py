from datetime import datetime, date, timezone, timedelta
from app.models.transacao import Transacao
from app.models.conta import Conta
from app.models.cartao import Cartao


def test_regra_1_bloqueios_saque_e_transferencia(client):
    # Cria cliente ativo e cliente bloqueado
    cli_ativo = client.post(
        "/clientes",
        json={
            "nome": "Ativo",
            "cpf": "12345678909",
            "email": "ativo@example.com",
            "categoria": "comum",
            "situacao": "ativo",
        },
    ).json()

    cli_bloqueado = client.post(
        "/clientes",
        json={
            "nome": "Bloqueado",
            "cpf": "98765432100",
            "email": "bloq@example.com",
            "categoria": "comum",
            "situacao": "bloqueado",
        },
    ).json()

    # Conta ativa de cliente ativo
    c_ativa = client.post(
        "/contas",
        json={
            "cliente_id": cli_ativo["id"],
            "numero": "C-ATIVA",
            "tipo": "corrente",
            "saldo_inicial": 1000.0,
            "limite_credito": 500.0,
        },
    ).json()

    # Conta bloqueada de cliente ativo
    c_bloqueada = client.post(
        "/contas",
        json={
            "cliente_id": cli_ativo["id"],
            "numero": "C-BLOQ",
            "tipo": "corrente",
            "saldo_inicial": 1000.0,
            "limite_credito": 500.0,
        },
    ).json()
    client.put(f"/contas/{c_bloqueada['id']}", json={"estado": "bloqueada"})

    # Conta de cliente bloqueado
    c_cli_bloq = client.post(
        "/contas",
        json={
            "cliente_id": cli_bloqueado["id"],
            "numero": "C-CLI-BLOQ",
            "tipo": "corrente",
            "saldo_inicial": 1000.0,
            "limite_credito": 500.0,
        },
    ).json()

    # 1. Saque em conta bloqueada deve falhar
    res1 = client.post("/transacoes/saque", json={"conta_id": c_bloqueada["id"], "valor": 100.0})
    assert res1.status_code == 400
    assert "bloqueada" in res1.json()["detail"].lower()

    # 2. Saque de cliente bloqueado deve falhar
    res2 = client.post("/transacoes/saque", json={"conta_id": c_cli_bloq["id"], "valor": 100.0})
    assert res2.status_code == 400
    assert "bloqueado" in res2.json()["detail"].lower()

    # 3. Transferência a partir de conta bloqueada deve falhar
    res3 = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": c_bloqueada["id"], "conta_destino_id": c_ativa["id"], "valor": 100.0},
    )
    assert res3.status_code == 400

    # 4. Transferência de cliente bloqueado deve falhar
    res4 = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": c_cli_bloq["id"], "conta_destino_id": c_ativa["id"], "valor": 100.0},
    )
    assert res4.status_code == 400

    # 5. Transferência para conta bloqueada deve falhar
    res5 = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": c_ativa["id"], "conta_destino_id": c_bloqueada["id"], "valor": 100.0},
    )
    assert res5.status_code == 400


def test_regra_1_limite_transferencia_premium(client):
    # Premium: limite por transferência R$ 50.000,00
    cli = client.post(
        "/clientes",
        json={
            "nome": "Cliente Premium",
            "cpf": "12345678909",
            "email": "prem@example.com",
            "categoria": "premium",
        },
    ).json()

    c1 = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "PREM-C1",
            "tipo": "corrente",
            "saldo_inicial": 100000.0,
            "limite_credito": 0.0,
        },
    ).json()

    c2 = client.post(
        "/contas",
        json={
            "cliente_id": cli["id"],
            "numero": "PREM-C2",
            "tipo": "corrente",
            "saldo_inicial": 0.0,
            "limite_credito": 0.0,
        },
    ).json()

    # Transferência de 50.000,00 deve ser permitida
    res_ok = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": c1["id"], "conta_destino_id": c2["id"], "valor": 50000.0},
    )
    assert res_ok.status_code == 201

    # Transferência de 50.000,01 deve ser negada
    res_negada = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": c1["id"], "conta_destino_id": c2["id"], "valor": 50000.01},
    )
    assert res_negada.status_code == 400
    assert "limite por transferência excedido" in res_negada.json()["detail"].lower()


def test_regra_3_premium_transacoes_isentas_ilimitadas(client):
    # Premium: transações isentas ilimitadas (não gera tarifa mesmo para terceiros)
    cli_prem = client.post(
        "/clientes",
        json={
            "nome": "Premium",
            "cpf": "12345678909",
            "email": "prem2@example.com",
            "categoria": "premium",
        },
    ).json()

    cli_outro = client.post(
        "/clientes",
        json={
            "nome": "Outro",
            "cpf": "98765432100",
            "email": "outro2@example.com",
            "categoria": "comum",
        },
    ).json()

    c_origem = client.post(
        "/contas",
        json={"cliente_id": cli_prem["id"], "numero": "C-PREM", "saldo_inicial": 10000.0, "limite_credito": 0.0},
    ).json()

    c_destino = client.post(
        "/contas",
        json={"cliente_id": cli_outro["id"], "numero": "C-OUTRO", "saldo_inicial": 0.0, "limite_credito": 0.0},
    ).json()

    # Faz 10 transferências de R$ 50 para terceiro
    for _ in range(10):
        res = client.post(
            "/transacoes/transferencia",
            json={"conta_origem_id": c_origem["id"], "conta_destino_id": c_destino["id"], "valor": 50.0},
        )
        assert res.status_code == 201

    # Todas as tarifas devem ser isentas!
    tarifas = client.get(f"/contas/{c_origem['id']}/tarifas").json()
    assert len(tarifas) == 10
    assert all(t["estado"] == "isenta" for t in tarifas)
    assert float(client.get(f"/contas/{c_origem['id']}").json()["saldo"]) == 9500.0


def test_regra_4_estorno_apos_24_horas_falha(client, db_session):
    cli = client.post(
        "/clientes",
        json={"nome": "Estorno Tempo", "cpf": "12345678909", "email": "tempo@example.com", "categoria": "comum"},
    ).json()

    conta = client.post(
        "/contas",
        json={"cliente_id": cli["id"], "numero": "C-TEMPO", "saldo_inicial": 500.0, "limite_credito": 0.0},
    ).json()

    tx = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 100.0}).json()

    # Altera a data da transação para 25 horas atrás
    tx_db = db_session.query(Transacao).filter(Transacao.id == tx["id"]).first()
    tx_db.data = datetime.now(timezone.utc) - timedelta(hours=25)
    db_session.commit()

    res_est = client.post(f"/transacoes/{tx['id']}/estorno")
    assert res_est.status_code == 400
    assert "24 horas" in res_est.json()["detail"].lower()


def test_regra_4_estorno_deposito_e_saldo_insuficiente(client):
    cli = client.post(
        "/clientes",
        json={"nome": "Estorno Dep", "cpf": "12345678909", "email": "depinsuf@example.com", "categoria": "comum"},
    ).json()

    conta = client.post(
        "/contas",
        json={"cliente_id": cli["id"], "numero": "C-DEPINSUF", "saldo_inicial": 0.0, "limite_credito": 50.0},
    ).json()

    # Faz depósito de 200.0
    dep = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 200.0}).json()

    # Gasta 180.0 com saque (saldo fica 20.0, limite = 50.0 -> total disponível = 70.0)
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 180.0})

    # Tenta estornar o depósito de 200.0 (precisaria de 200.0, mas tem apenas 70.0 disponível)
    res_est = client.post(f"/transacoes/{dep['id']}/estorno")
    assert res_est.status_code == 400
    assert "suficiente" in res_est.json()["detail"].lower()


def test_regra_5_juros_premium_e_empresarial(client):
    # Premium: juros de atraso 5% ao mês (0.05)
    # Empresarial: juros de atraso 3% ao mês (0.03)
    cli_prem = client.post(
        "/clientes",
        json={"nome": "Cli Prem", "cpf": "12345678909", "email": "prem_jur@example.com", "categoria": "premium"},
    ).json()

    cli_emp = client.post(
        "/clientes",
        json={"nome": "Cli Emp", "cpf": "98765432100", "email": "emp_jur@example.com", "categoria": "empresarial"},
    ).json()

    c_prem = client.post(
        "/contas", json={"cliente_id": cli_prem["id"], "numero": "CP-1", "saldo_inicial": 1000.0, "limite_credito": 0.0}
    ).json()

    c_emp = client.post(
        "/contas", json={"cliente_id": cli_emp["id"], "numero": "CE-1", "saldo_inicial": 1000.0, "limite_credito": 0.0}
    ).json()

    card_prem = client.post(
        "/cartoes", json={"conta_id": c_prem["id"], "numero": "CARD-PREM-1", "limite": 5000.0}
    ).json()

    card_emp = client.post(
        "/cartoes", json={"conta_id": c_emp["id"], "numero": "CARD-EMP-1", "limite": 10000.0}
    ).json()

    # Atraso de 30 dias (1 mês exato)
    vencimento_30d = (date.today() - timedelta(days=30)).isoformat()

    fat_prem = client.post(
        f"/cartoes/{card_prem['id']}/faturas",
        json={"cartao_id": card_prem["id"], "mes_referencia": "2026-09", "valor": 1000.0, "data_vencimento": vencimento_30d},
    ).json()

    fat_emp = client.post(
        f"/cartoes/{card_emp['id']}/faturas",
        json={"cartao_id": card_emp["id"], "mes_referencia": "2026-09", "valor": 1000.0, "data_vencimento": vencimento_30d},
    ).json()

    # Premium: 1000 * 0.05 * (30 / 30) = 50.00 de juros
    assert float(fat_prem["juros_acumulados"]) == 50.0
    assert float(fat_prem["valor_total"]) == 1050.0

    # Empresarial: 1000 * 0.03 * (30 / 30) = 30.00 de juros
    assert float(fat_emp["juros_acumulados"]) == 30.0
    assert float(fat_emp["valor_total"]) == 1030.0


def test_regra_5_atraso_ate_10_dias_nao_bloqueia_cartao(client):
    cli = client.post(
        "/clientes",
        json={"nome": "Cli 5 dias", "cpf": "12345678909", "email": "cinco@example.com", "categoria": "comum"},
    ).json()

    conta = client.post(
        "/contas", json={"cliente_id": cli["id"], "numero": "C-5D", "saldo_inicial": 1000.0, "limite_credito": 0.0}
    ).json()

    cartao = client.post(
        "/cartoes", json={"conta_id": conta["id"], "numero": "CARD-5D", "limite": 2000.0}
    ).json()

    # Fatura vencida há 5 dias (<= 10 dias de atraso)
    vencimento_5d = (date.today() - timedelta(days=5)).isoformat()
    fatura = client.post(
        f"/cartoes/{cartao['id']}/faturas",
        json={"cartao_id": cartao["id"], "mes_referencia": "2026-10", "valor": 500.0, "data_vencimento": vencimento_5d},
    ).json()

    assert fatura["estado"] == "atrasada"
    # Cartão deve continuar ATIVO pois não ultrapassou 10 dias de atraso
    cartao_check = client.get(f"/cartoes/{cartao['id']}").json()
    assert cartao_check["estado"] == "ativo"


def test_regra_7_encerramento_conta_com_fatura_aberta_falha(client):
    cli = client.post(
        "/clientes",
        json={"nome": "Cli Encerrar Fat", "cpf": "12345678909", "email": "encfat@example.com", "categoria": "comum"},
    ).json()

    conta = client.post(
        "/contas", json={"cliente_id": cli["id"], "numero": "C-ENC-FAT", "saldo_inicial": 0.0, "limite_credito": 0.0}
    ).json()

    cartao = client.post(
        "/cartoes", json={"conta_id": conta["id"], "numero": "CARD-ENC-FAT", "limite": 1000.0}
    ).json()

    vencimento_futuro = (date.today() + timedelta(days=20)).isoformat()
    client.post(
        f"/cartoes/{cartao['id']}/faturas",
        json={"cartao_id": cartao["id"], "mes_referencia": "2026-11", "valor": 100.0, "data_vencimento": vencimento_futuro},
    )

    # Tenta encerrar conta que tem fatura aberta vinculada ao cartão
    res = client.post(f"/contas/{conta['id']}/encerrar")
    assert res.status_code == 400
    assert "faturas abertas" in res.json()["detail"].lower() or "faturas" in res.json()["detail"].lower()


def test_tarifas_mensais_por_categoria(client):
    # Comum: R$ 30,00 | Premium: R$ 0,00 | Empresarial: R$ 120,00
    cli_c = client.post(
        "/clientes", json={"nome": "Comum", "cpf": "12345678909", "email": "c@ex.com", "categoria": "comum"}
    ).json()
    cli_p = client.post(
        "/clientes", json={"nome": "Premium", "cpf": "98765432100", "email": "p@ex.com", "categoria": "premium"}
    ).json()
    cli_e = client.post(
        "/clientes", json={"nome": "Empresarial", "cpf": "96371727184", "email": "e@ex.com", "categoria": "empresarial"}
    ).json()

    conta_c = client.post("/contas", json={"cliente_id": cli_c["id"], "numero": "TC-1", "saldo_inicial": 100.0, "limite_credito": 0.0}).json()
    conta_p = client.post("/contas", json={"cliente_id": cli_p["id"], "numero": "TP-1", "saldo_inicial": 100.0, "limite_credito": 0.0}).json()
    conta_e = client.post("/contas", json={"cliente_id": cli_e["id"], "numero": "TE-1", "saldo_inicial": 200.0, "limite_credito": 0.0}).json()

    # Cobrança Comum
    tar_c = client.post(f"/contas/{conta_c['id']}/tarifas/cobrar-mensalidade").json()
    assert float(tar_c["valor"]) == 30.0
    assert tar_c["estado"] == "cobrada"
    assert float(client.get(f"/contas/{conta_c['id']}").json()["saldo"]) == 70.0

    # Cobrança Premium (sem tarifa mensal -> R$ 0,00 e isenta)
    tar_p = client.post(f"/contas/{conta_p['id']}/tarifas/cobrar-mensalidade").json()
    assert float(tar_p["valor"]) == 0.0
    assert tar_p["estado"] == "isenta"
    assert float(client.get(f"/contas/{conta_p['id']}").json()["saldo"]) == 100.0

    # Cobrança Empresarial
    tar_e = client.post(f"/contas/{conta_e['id']}/tarifas/cobrar-mensalidade").json()
    assert float(tar_e["valor"]) == 120.0
    assert tar_e["estado"] == "cobrada"
    assert float(client.get(f"/contas/{conta_e['id']}").json()["saldo"]) == 80.0
