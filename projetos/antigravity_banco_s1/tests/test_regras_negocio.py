from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest

from app.models.cartao import EstadoCartao
from app.models.cliente import SituacaoCliente
from app.models.conta import Conta, EstadoConta
from app.models.fatura import EstadoFatura, Fatura
from app.models.transacao import EstadoTransacao, Transacao
from tests.conftest import gerar_cpf_valido


def test_regra_1_conta_ou_cliente_bloqueado(client):
    # Cliente Comum Bloqueado
    cpf = gerar_cpf_valido(801)
    cli = client.post(
        "/clientes",
        json={"nome": "Cli Bloq", "cpf": cpf, "email": "bloq@test.com", "categoria": "comum", "situacao": "bloqueado"},
    ).json()["id"]

    cta = client.post(
        "/contas",
        json={"cliente_id": cli, "numero": "CTA-BLOQ-1", "tipo": "corrente", "limite_credito": "1000.00"},
    ).json()["id"]

    client.post("/transacoes/deposito", json={"conta_id": cta, "valor": "500.00"})

    # Tentativa de saque com cliente bloqueado deve falhar
    res_saque = client.post("/transacoes/saque", json={"conta_id": cta, "valor": "100.00"})
    assert res_saque.status_code == 400
    assert "bloqueado" in res_saque.json()["detail"].lower()

    # Desbloqueia cliente, mas bloqueia a conta
    client.put(f"/clientes/{cli}", json={"situacao": "ativo"})
    client.put(f"/contas/{cta}", json={"estado": "bloqueada"})

    res_saque2 = client.post("/transacoes/saque", json={"conta_id": cta, "valor": "100.00"})
    assert res_saque2.status_code == 400
    assert "bloqueada" in res_saque2.json()["detail"].lower()


def test_regra_1_limite_diario_saque_por_categoria(client):
    # 1. Comum: R$ 1.000,00 diário
    cli_c = client.post(
        "/clientes",
        json={"nome": "Comum", "cpf": gerar_cpf_valido(810), "email": "c@lim.com", "categoria": "comum"},
    ).json()["id"]
    cta_c = client.post(
        "/contas",
        json={"cliente_id": cli_c, "numero": "CTA-C", "limite_credito": "2000.00"},
    ).json()["id"]
    client.post("/transacoes/deposito", json={"conta_id": cta_c, "valor": "5000.00"})

    # Primeiro saque de 700 (OK)
    r1 = client.post("/transacoes/saque", json={"conta_id": cta_c, "valor": "700.00"})
    assert r1.status_code == 201

    # Segundo saque de 301 excede o limite diário de 1.000,00
    r2 = client.post("/transacoes/saque", json={"conta_id": cta_c, "valor": "301.00"})
    assert r2.status_code == 400
    assert "Limite diário de saque excedido" in r2.json()["detail"]

    # 2. Premium: R$ 5.000,00 diário
    cli_p = client.post(
        "/clientes",
        json={"nome": "Premium", "cpf": gerar_cpf_valido(811), "email": "p@lim.com", "categoria": "premium"},
    ).json()["id"]
    cta_p = client.post(
        "/contas",
        json={"cliente_id": cli_p, "numero": "CTA-P", "limite_credito": "10000.00"},
    ).json()["id"]
    client.post("/transacoes/deposito", json={"conta_id": cta_p, "valor": "10000.00"})

    rp1 = client.post("/transacoes/saque", json={"conta_id": cta_p, "valor": "5000.00"})
    assert rp1.status_code == 201
    rp2 = client.post("/transacoes/saque", json={"conta_id": cta_p, "valor": "1.00"})
    assert rp2.status_code == 400
    assert "Limite diário de saque excedido" in rp2.json()["detail"]

    # 3. Empresarial: R$ 20.000,00 diário
    cli_e = client.post(
        "/clientes",
        json={"nome": "Empresarial", "cpf": gerar_cpf_valido(812), "email": "e@lim.com", "categoria": "empresarial"},
    ).json()["id"]
    cta_e = client.post(
        "/contas",
        json={"cliente_id": cli_e, "numero": "CTA-E", "limite_credito": "30000.00"},
    ).json()["id"]
    client.post("/transacoes/deposito", json={"conta_id": cta_e, "valor": "30000.00"})

    re1 = client.post("/transacoes/saque", json={"conta_id": cta_e, "valor": "20000.00"})
    assert re1.status_code == 201
    re2 = client.post("/transacoes/saque", json={"conta_id": cta_e, "valor": "1.00"})
    assert re2.status_code == 400
    assert "Limite diário de saque excedido" in re2.json()["detail"]


def test_regra_1_limite_por_transferencia_por_categoria(client):
    # Comum: máx R$ 5.000,00 por transferência
    cli_c = client.post(
        "/clientes", json={"nome": "Comum T", "cpf": gerar_cpf_valido(820), "email": "ct@test.com", "categoria": "comum"}
    ).json()["id"]
    cta_c = client.post("/contas", json={"cliente_id": cli_c, "numero": "CTA-T-C", "limite_credito": "50000.00"}).json()["id"]
    client.post("/transacoes/deposito", json={"conta_id": cta_c, "valor": "50000.00"})

    # Destino
    cli_d = client.post(
        "/clientes", json={"nome": "Destino", "cpf": gerar_cpf_valido(821), "email": "dt@test.com", "categoria": "comum"}
    ).json()["id"]
    cta_d = client.post("/contas", json={"cliente_id": cli_d, "numero": "CTA-T-D", "limite_credito": "0.00"}).json()["id"]

    # Tentativa de 5001.00 deve falhar
    res_fail = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": cta_c, "conta_destino_id": cta_d, "valor": "5001.00"},
    )
    assert res_fail.status_code == 400
    assert "Limite por transferência excedido" in res_fail.json()["detail"]

    # Transferência de 5000.00 deve ter sucesso
    res_ok = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": cta_c, "conta_destino_id": cta_d, "valor": "5000.00"},
    )
    assert res_ok.status_code == 201


def test_regra_2_saldo_negativo_ate_o_limite_de_credito(client):
    cli = client.post(
        "/clientes", json={"nome": "Credito", "cpf": gerar_cpf_valido(830), "email": "cred@test.com", "categoria": "comum"}
    ).json()["id"]
    # Saldo inicial 0, limite 800
    cta = client.post("/contas", json={"cliente_id": cli, "numero": "CTA-CRED", "limite_credito": "800.00"}).json()["id"]

    # Saque de 800 (OK, saldo vai para -800)
    r1 = client.post("/transacoes/saque", json={"conta_id": cta, "valor": "800.00"})
    assert r1.status_code == 201
    conta_atual = client.get(f"/contas/{cta}").json()
    assert conta_atual["saldo"] == "-800.00"
    assert conta_atual["data_saldo_negativo"] is not None

    # Novo saque de qualquer valor acima do limite disponível deve falhar
    r2 = client.post("/transacoes/saque", json={"conta_id": cta, "valor": "1.00"})
    assert r2.status_code == 400
    assert "Saldo insuficiente" in r2.json()["detail"]

    # Faz depósito que volta o saldo para >= 0
    client.post("/transacoes/deposito", json={"conta_id": cta, "valor": "900.00"})
    conta_restaurada = client.get(f"/contas/{cta}").json()
    assert conta_restaurada["saldo"] == "100.00"
    assert conta_restaurada["data_saldo_negativo"] is None


def test_regra_3_franquia_e_tarifa_de_transferencias(client):
    # Cliente Comum: 3 transferências isentas por mês
    cli1 = client.post(
        "/clientes", json={"nome": "Cli 1", "cpf": gerar_cpf_valido(840), "email": "franquia1@test.com", "categoria": "comum"}
    ).json()["id"]
    cta1_a = client.post("/contas", json={"cliente_id": cli1, "numero": "C1-A", "limite_credito": "1000.00"}).json()["id"]
    cta1_b = client.post("/contas", json={"cliente_id": cli1, "numero": "C1-B", "limite_credito": "1000.00"}).json()["id"]

    cli2 = client.post(
        "/clientes", json={"nome": "Cli 2", "cpf": gerar_cpf_valido(841), "email": "franquia2@test.com", "categoria": "comum"}
    ).json()["id"]
    cta2 = client.post("/contas", json={"cliente_id": cli2, "numero": "C2-A", "limite_credito": "0.00"}).json()["id"]

    client.post("/transacoes/deposito", json={"conta_id": cta1_a, "valor": "2000.00"})

    # 1. Transferência entre contas do MESMO cliente: isenta, não gasta franquia
    res_mesmo = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": cta1_a, "conta_destino_id": cta1_b, "valor": "100.00"},
    )
    assert res_mesmo.status_code == 201
    # Verifica que não houve cobrança de tarifa
    tarifas_c1 = client.get(f"/contas/{cta1_a}/tarifas?estado=cobrada").json()
    assert len(tarifas_c1) == 0

    # 2. Faz 3 transferências para conta de OUTRO cliente (todas isentas pela franquia de 3)
    for i in range(3):
        res = client.post(
            "/transacoes/transferencia",
            json={"conta_origem_id": cta1_a, "conta_destino_id": cta2, "valor": "50.00"},
        )
        assert res.status_code == 201

    tarifas_cobradas = client.get(f"/contas/{cta1_a}/tarifas?estado=cobrada").json()
    assert len(tarifas_cobradas) == 0

    # 3. Quarta transferência para OUTRO cliente: esgotou a franquia de 3, GERA TARIFA
    saldo_antes = Decimal(client.get(f"/contas/{cta1_a}").json()["saldo"])
    res_quarta = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": cta1_a, "conta_destino_id": cta2, "valor": "50.00"},
    )
    assert res_quarta.status_code == 201
    saldo_depois = Decimal(client.get(f"/contas/{cta1_a}").json()["saldo"])

    # Saldo deve ter debitado 50.00 + 10.00 da tarifa = 60.00
    assert saldo_antes - saldo_depois == Decimal("60.00")

    # Verifica se a tarifa foi registrada como COBRADA
    tarifas_cobradas = client.get(f"/contas/{cta1_a}/tarifas?estado=cobrada").json()
    assert len(tarifas_cobradas) == 1
    assert tarifas_cobradas[0]["valor"] == "10.00"
    assert tarifas_cobradas[0]["tipo"] == "transferencia"


def test_regra_4_estorno_em_ate_24_horas(client, db_session):
    cli1 = client.post(
        "/clientes", json={"nome": "Cli E1", "cpf": gerar_cpf_valido(850), "email": "e1@test.com", "categoria": "comum"}
    ).json()["id"]
    cli2 = client.post(
        "/clientes", json={"nome": "Cli E2", "cpf": gerar_cpf_valido(851), "email": "e2@test.com", "categoria": "comum"}
    ).json()["id"]

    cta1 = client.post("/contas", json={"cliente_id": cli1, "numero": "CTA-E1", "limite_credito": "100.00"}).json()["id"]
    cta2 = client.post("/contas", json={"cliente_id": cli2, "numero": "CTA-E2", "limite_credito": "100.00"}).json()["id"]

    # 1. Estorno de depósito
    dep = client.post("/transacoes/deposito", json={"conta_id": cta1, "valor": "300.00"}).json()
    assert client.get(f"/contas/{cta1}").json()["saldo"] == "300.00"

    res_estorno_dep = client.post(f"/transacoes/{dep['id']}/estorno")
    assert res_estorno_dep.status_code == 201
    assert client.get(f"/contas/{cta1}").json()["saldo"] == "0.00"

    # Não pode estornar duas vezes
    res_estorno_duplo = client.post(f"/transacoes/{dep['id']}/estorno")
    assert res_estorno_duplo.status_code == 400

    # 2. Estorno de transferência
    client.post("/transacoes/deposito", json={"conta_id": cta1, "valor": "500.00"})
    transf = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": cta1, "conta_destino_id": cta2, "valor": "200.00"},
    ).json()

    assert client.get(f"/contas/{cta1}").json()["saldo"] == "300.00"
    assert client.get(f"/contas/{cta2}").json()["saldo"] == "200.00"

    res_estorno_tr = client.post(f"/transacoes/{transf['id']}/estorno")
    assert res_estorno_tr.status_code == 201
    assert client.get(f"/contas/{cta1}").json()["saldo"] == "500.00"
    assert client.get(f"/contas/{cta2}").json()["saldo"] == "0.00"

    # 3. Transação com mais de 24 horas não pode ser estornada
    tx = db_session.query(Transacao).filter(Transacao.id == res_estorno_tr.json()["id"]).first()
    # Cria uma transação fake com 25 horas no passado
    tx_antiga = Transacao(
        conta_id=cta1,
        tipo=Transacao.tipo.property.columns[0].type.enum_class.SAQUE,
        valor=Decimal("50.00"),
        data=datetime.now(timezone.utc) - timedelta(hours=25),
        estado=Transacao.estado.property.columns[0].type.enum_class.EFETIVADA,
    )
    db_session.add(tx_antiga)
    db_session.commit()
    db_session.refresh(tx_antiga)

    res_antiga = client.post(f"/transacoes/{tx_antiga.id}/estorno")
    assert res_antiga.status_code == 400
    assert "24 horas" in res_antiga.json()["detail"]


def test_regra_5_fatura_atrasada_juros_e_bloqueio_cartao_10_dias(client, db_session):
    # Cliente Comum: juros de 8% ao mês
    cli = client.post(
        "/clientes", json={"nome": "Cli Juros", "cpf": gerar_cpf_valido(860), "email": "juros@test.com", "categoria": "comum"}
    ).json()["id"]
    cta = client.post("/contas", json={"cliente_id": cli, "numero": "CTA-FAT", "limite_credito": "100.00"}).json()["id"]
    cartao = client.post("/cartoes", json={"conta_id": cta, "numero": "CARD-FAT-1", "limite": "2000.00"}).json()["id"]

    # Fatura de R$ 1.000,00 que venceu há 15 dias
    data_vencimento = date.today() - timedelta(days=15)
    fatura = client.post(
        f"/cartoes/{cartao}/faturas",
        json={"mes_referencia": "2026-10", "valor": "1000.00", "data_vencimento": str(data_vencimento)},
    ).json()["id"]

    # Executa a verificação de atrasos
    res_rotina = client.post("/faturas/verificar-atrasos")
    assert res_rotina.status_code == 200
    assert res_rotina.json()["cartoes_bloqueados"] == 1

    # Verifica fatura atualizada
    fatura_atualizada = client.get(f"/faturas/{fatura}").json()
    assert fatura_atualizada["estado"] == "atrasada"
    # Juros Comum: 8% ao mês pro-rata: 1000 * 0.08 * (15 / 30) = 40.00
    assert Decimal(fatura_atualizada["juros_acumulados"]) == Decimal("40.00")
    assert Decimal(fatura_atualizada["valor_total_devido"]) == Decimal("1040.00")

    # Verifica cartão bloqueado após > 10 dias de atraso
    cartao_atual = client.get(f"/cartoes/{cartao}").json()
    assert cartao_atual["estado"] == "bloqueado"


def test_regra_6_saldo_negativo_por_mais_de_30_dias(client, db_session):
    cli = client.post(
        "/clientes", json={"nome": "Cli Negativo", "cpf": gerar_cpf_valido(870), "email": "neg30@test.com", "categoria": "comum"}
    ).json()["id"]
    cta = client.post("/contas", json={"cliente_id": cli, "numero": "CTA-NEG30", "limite_credito": "1000.00"}).json()["id"]
    card1 = client.post("/cartoes", json={"conta_id": cta, "numero": "CARD-NEG-1", "limite": "500.00"}).json()["id"]
    card2 = client.post("/cartoes", json={"conta_id": cta, "numero": "CARD-NEG-2", "limite": "500.00"}).json()["id"]

    # Faz saque e deixa saldo negativo em -500
    client.post("/transacoes/saque", json={"conta_id": cta, "valor": "500.00"})

    # Simula que a conta ficou negativa há 35 dias
    conta_db = db_session.query(Conta).filter(Conta.id == cta).first()
    conta_db.data_saldo_negativo = datetime.now(timezone.utc) - timedelta(days=35)
    db_session.commit()

    # Roda a rotina de verificação de inadimplência
    res_inad = client.post("/rotinas/verificar-inadimplencia")
    assert res_inad.status_code == 200
    assert res_inad.json()["saldo_negativo_30_dias"]["clientes_bloqueados"] == 1
    assert res_inad.json()["saldo_negativo_30_dias"]["cartoes_bloqueados"] == 2

    # Verifica cliente bloqueado
    cli_db = client.get(f"/clientes/{cli}").json()
    assert cli_db["situacao"] == "bloqueado"

    # Verifica todos os cartões bloqueados
    c1_db = client.get(f"/cartoes/{card1}").json()
    c2_db = client.get(f"/cartoes/{card2}").json()
    assert c1_db["estado"] == "bloqueado"
    assert c2_db["estado"] == "bloqueado"


def test_transferencia_mesma_conta_rejeitada(client):
    cli = client.post(
        "/clientes", json={"nome": "Cli Same", "cpf": gerar_cpf_valido(880), "email": "same@test.com", "categoria": "comum"}
    ).json()["id"]
    cta = client.post("/contas", json={"cliente_id": cli, "numero": "CTA-SAME", "limite_credito": "100.00"}).json()["id"]

    res = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": cta, "conta_destino_id": cta, "valor": "50.00"},
    )
    assert res.status_code == 400
    assert "não podem ser as mesmas" in res.json()["detail"]


def test_estorno_deposito_sem_saldo_ou_limite_para_reverter(client):
    cli = client.post(
        "/clientes", json={"nome": "Cli Est Sem Saldo", "cpf": gerar_cpf_valido(881), "email": "estrev@test.com", "categoria": "comum"}
    ).json()["id"]
    # Limite 0
    cta = client.post("/contas", json={"cliente_id": cli, "numero": "CTA-EST-SEM", "limite_credito": "0.00"}).json()["id"]

    # Depósito de 500
    dep = client.post("/transacoes/deposito", json={"conta_id": cta, "valor": "500.00"}).json()["id"]

    # Saque de 400 (saldo restante: 100)
    client.post("/transacoes/saque", json={"conta_id": cta, "valor": "400.00"})

    # Tentar estornar o depósito de 500 necessitaria deduzir 500, mas saldo disponível é apenas 100
    res_est = client.post(f"/transacoes/{dep}/estorno")
    assert res_est.status_code == 400
    assert "não possui saldo/limite suficiente" in res_est.json()["detail"]


def test_saldo_negativo_menos_de_30_dias_nao_bloqueia(client, db_session):
    cli = client.post(
        "/clientes", json={"nome": "Cli 25 Dias", "cpf": gerar_cpf_valido(882), "email": "dias25@test.com", "categoria": "comum"}
    ).json()["id"]
    cta = client.post("/contas", json={"cliente_id": cli, "numero": "CTA-25D", "limite_credito": "1000.00"}).json()["id"]
    card = client.post("/cartoes", json={"conta_id": cta, "numero": "CARD-25D", "limite": "500.00"}).json()["id"]

    # Saque negativo
    client.post("/transacoes/saque", json={"conta_id": cta, "valor": "300.00"})

    # 25 dias no negativo (menos de 30 dias)
    conta_db = db_session.query(Conta).filter(Conta.id == cta).first()
    conta_db.data_saldo_negativo = datetime.now(timezone.utc) - timedelta(days=25)
    db_session.commit()

    res_inad = client.post("/rotinas/verificar-inadimplencia")
    assert res_inad.status_code == 200
    assert res_inad.json()["saldo_negativo_30_dias"]["clientes_bloqueados"] == 0

    # Cliente e cartão continuam ativos
    assert client.get(f"/clientes/{cli}").json()["situacao"] == "ativo"
    assert client.get(f"/cartoes/{card}").json()["estado"] == "ativo"


def test_fatura_atrasada_menos_de_10_dias_nao_bloqueia_cartao(client):
    cli = client.post(
        "/clientes", json={"nome": "Cli Fat 5 Dias", "cpf": gerar_cpf_valido(883), "email": "fat5d@test.com", "categoria": "comum"}
    ).json()["id"]
    cta = client.post("/contas", json={"cliente_id": cli, "numero": "CTA-FAT-5D", "limite_credito": "500.00"}).json()["id"]
    card = client.post("/cartoes", json={"conta_id": cta, "numero": "CARD-FAT-5D", "limite": "1000.00"}).json()["id"]

    # Venceu há 5 dias (<= 10 dias)
    vencimento = date.today() - timedelta(days=5)
    client.post(
        f"/cartoes/{card}/faturas",
        json={"mes_referencia": "2026-10", "valor": "200.00", "data_vencimento": str(vencimento)},
    )

    client.post("/faturas/verificar-atrasos")
    # Cartão deve permanecer ativo
    assert client.get(f"/cartoes/{card}").json()["estado"] == "ativo"


def test_tarifa_mensal_saldo_insuficiente_fica_pendente(client):
    cli = client.post(
        "/clientes", json={"nome": "Cli Pendente", "cpf": gerar_cpf_valido(884), "email": "pend@test.com", "categoria": "comum"}
    ).json()["id"]
    # Limite 0 e saldo 0 (Comum tarifa mensal é 30.00)
    cta = client.post("/contas", json={"cliente_id": cli, "numero": "CTA-PEND", "limite_credito": "0.00"}).json()["id"]

    res_tar = client.post(f"/contas/{cta}/tarifas/cobrar-mensalidade")
    assert res_tar.status_code == 201
    assert res_tar.json()["estado"] == "pendente"

