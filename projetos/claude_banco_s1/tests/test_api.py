from datetime import timedelta

from app import clock
from tests.conftest import AGORA


def saldo(client, conta_id):
    return client.get(f"/contas/{conta_id}").json()["saldo"]


# ---------------- Validacao / CRUD ----------------
def test_validacao_cliente(client, novo_cliente):
    base = {"nome": "Ana", "cpf": "52998224725", "email": "ana@banco.com.br", "categoria": "comum"}
    assert client.post("/clientes", json={**base, "cpf": "12345678900"}).status_code == 422
    assert client.post("/clientes", json={**base, "email": "invalido"}).status_code == 422
    assert client.post("/clientes", json={**base, "categoria": "vip"}).status_code == 422
    assert client.post("/clientes", json={**base, "campo_extra": 1}).status_code == 422
    r = client.post("/clientes", json={**base, "cpf": "529.982.247-25"})
    assert r.status_code == 201 and r.json()["cpf"] == "52998224725" and r.json()["situacao"] == "ativo"
    assert client.post("/clientes", json={**base, "email": "outro@banco.com.br"}).status_code == 409
    assert client.get("/clientes/999").status_code == 404


def test_crud_cliente(client, novo_cliente, nova_conta):
    c = novo_cliente()
    r = client.patch(f"/clientes/{c['id']}", json={"categoria": "premium"})
    assert r.status_code == 200 and r.json()["categoria"] == "premium"
    assert len(client.get("/clientes", params={"categoria": "premium"}).json()) == 1
    nova_conta(cliente_id=c["id"])
    assert client.delete(f"/clientes/{c['id']}").status_code == 409
    c2 = novo_cliente()
    assert client.delete(f"/clientes/{c2['id']}").status_code == 204
    assert client.get(f"/clientes/{c2['id']}").status_code == 404


def test_valores_monetarios_validados(client, nova_conta):
    conta = nova_conta()
    assert client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 0}).status_code == 422
    assert client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": -5}).status_code == 422
    assert client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 1.234}).status_code == 422
    assert client.post("/transacoes/deposito", json={"conta_id": 999, "valor": 10}).status_code == 404
    r = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 0.1})
    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 0.2})
    assert r.status_code == 201
    assert saldo(client, conta["id"]) == 0.3


# ---------------- Regra 1 ----------------
def test_limite_diario_saque_comum(client, nova_conta):
    conta = nova_conta("comum", saldo=5000)
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 600}).status_code == 201
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 400}).status_code == 201
    r = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 0.01})
    assert r.status_code == 422 and "Limite diario" in r.json()["detail"]
    clock.fixar(AGORA + timedelta(days=1))
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 1000}).status_code == 201


def test_limite_diario_acumulado_por_cliente(client, novo_cliente, nova_conta):
    cli = novo_cliente("premium")
    c1 = nova_conta(cliente_id=cli["id"], saldo=10000)
    c2 = nova_conta(cliente_id=cli["id"], saldo=10000)
    assert client.post("/transacoes/saque", json={"conta_id": c1["id"], "valor": 3000}).status_code == 201
    assert client.post("/transacoes/saque", json={"conta_id": c2["id"], "valor": 2000}).status_code == 201
    assert client.post("/transacoes/saque", json={"conta_id": c2["id"], "valor": 1}).status_code == 422


def test_limite_diario_empresarial(client, nova_conta):
    conta = nova_conta("empresarial", saldo=50000)
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 20000}).status_code == 201
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 0.01}).status_code == 422


def test_limite_por_transferencia(client, nova_conta):
    for categoria, limite in (("comum", 5000), ("premium", 50000), ("empresarial", 200000)):
        origem = nova_conta(categoria, saldo=limite + 100)
        destino = nova_conta()
        corpo = {"conta_origem_id": origem["id"], "conta_destino_id": destino["id"]}
        assert client.post("/transacoes/transferencia", json={**corpo, "valor": limite + 0.01}).status_code == 422
        assert client.post("/transacoes/transferencia", json={**corpo, "valor": limite}).status_code == 201


def test_operacoes_exigem_conta_e_cliente_ativos(client, nova_conta):
    conta = nova_conta(saldo=500)
    client.patch(f"/contas/{conta['id']}", json={"estado": "bloqueada"})
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 10}).status_code == 409
    client.patch(f"/contas/{conta['id']}", json={"estado": "ativa"})
    client.patch(f"/clientes/{conta['cliente_id']}", json={"situacao": "bloqueado"})
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 10}).status_code == 409
    outra = nova_conta()
    r = client.post(
        "/transacoes/transferencia",
        json={"conta_origem_id": conta["id"], "conta_destino_id": outra["id"], "valor": 10},
    )
    assert r.status_code == 409
    # deposito continua permitido
    assert client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 10}).status_code == 201


# ---------------- Regra 2 ----------------
def test_limite_de_credito(client, nova_conta):
    conta = nova_conta("premium", saldo=100, limite_credito=200)
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 300.01}).status_code == 422
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 300}).status_code == 201
    c = client.get(f"/contas/{conta['id']}").json()
    assert c["saldo"] == -200 and c["negativo_desde"] is not None
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 0.01}).status_code == 422
    assert client.patch(f"/contas/{conta['id']}", json={"limite_credito": 100}).status_code == 422


# ---------------- Regra 3 ----------------
def test_franquia_e_tarifa_comum(client, nova_conta):
    conta = nova_conta("comum", saldo=1000)
    for _ in range(3):
        r = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 10})
        assert r.json()["tarifa"]["estado"] == "isenta"
    r = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 10})
    assert r.json()["tarifa"]["estado"] == "cobrada"
    assert r.json()["tarifa"]["valor"] == 5.0
    assert saldo(client, conta["id"]) == 1000 - 40 - 5
    tarifas = client.get(f"/contas/{conta['id']}/tarifas").json()
    assert [t["estado"] for t in tarifas] == ["isenta"] * 3 + ["cobrada"]
    # nova franquia no mes seguinte
    clock.fixar(AGORA + timedelta(days=20))
    r = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 10})
    assert r.json()["tarifa"]["estado"] == "isenta"


def test_transferencia_mesmo_cliente_isenta(client, novo_cliente, nova_conta):
    cli = novo_cliente("comum")
    a = nova_conta(cliente_id=cli["id"], saldo=1000)
    b = nova_conta(cliente_id=cli["id"])
    for _ in range(5):
        r = client.post(
            "/transacoes/transferencia", json={"conta_origem_id": a["id"], "conta_destino_id": b["id"], "valor": 10}
        )
        assert r.status_code == 201 and r.json()["tarifa"] is None
    assert saldo(client, a["id"]) == 950
    assert client.get(f"/contas/{a['id']}/tarifas").json() == []


def test_premium_isencao_ilimitada(client, nova_conta):
    conta = nova_conta("premium", saldo=1000)
    for _ in range(10):
        r = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 1})
        assert r.json()["tarifa"]["estado"] == "isenta"
    assert saldo(client, conta["id"]) == 990


def test_empresarial_franquia_50(client, nova_conta):
    conta = nova_conta("empresarial", saldo=1000)
    for _ in range(50):
        assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 1}).json()["tarifa"][
            "estado"
        ] == "isenta"
    r = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 1})
    assert r.json()["tarifa"]["estado"] == "cobrada"


def test_tarifa_considerada_no_limite(client, nova_conta):
    conta = nova_conta("comum", saldo=100)
    for _ in range(3):
        client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 10})
    # saldo 70; saque de 70 + tarifa 5 excede o limite (0)
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 70}).status_code == 422
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 65}).status_code == 201
    assert saldo(client, conta["id"]) == 0


# ---------------- Regra 4 ----------------
def test_estorno_transferencia(client, nova_conta):
    a = nova_conta("premium", saldo=1000)
    b = nova_conta()
    t = client.post(
        "/transacoes/transferencia", json={"conta_origem_id": a["id"], "conta_destino_id": b["id"], "valor": 300}
    ).json()["transacao"]
    r = client.post(f"/transacoes/{t['id']}/estorno")
    assert r.status_code == 201
    est = r.json()["transacao"]
    assert est["tipo"] == "estorno" and est["transacao_original_id"] == t["id"]
    assert saldo(client, a["id"]) == 1000 and saldo(client, b["id"]) == 0
    assert client.get(f"/transacoes/{t['id']}").json()["estado"] == "estornada"
    assert client.post(f"/transacoes/{t['id']}/estorno").status_code == 409
    assert client.post(f"/transacoes/{est['id']}/estorno").status_code == 409
    extrato = client.get(f"/contas/{a['id']}/extrato").json()
    assert [(l["transacao"]["tipo"], l["efeito"]) for l in extrato["lancamentos"]] == [
        ("deposito", 1000),
        ("transferencia", -300),
        ("estorno", 300),
    ]


def test_estorno_prazo_24h(client, nova_conta):
    conta = nova_conta("premium", saldo=1000)
    t = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 100}).json()["transacao"]
    clock.fixar(AGORA + timedelta(hours=24, seconds=1))
    assert client.post(f"/transacoes/{t['id']}/estorno").status_code == 422
    clock.fixar(AGORA + timedelta(hours=24))
    assert client.post(f"/transacoes/{t['id']}/estorno").status_code == 201
    assert saldo(client, conta["id"]) == 1000


def test_estorno_deposito_sem_saldo(client, nova_conta):
    conta = nova_conta("premium")
    dep = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 100}).json()["transacao"]
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 100})
    assert client.post(f"/transacoes/{dep['id']}/estorno").status_code == 422


def test_saque_estornado_libera_limite_diario(client, nova_conta):
    conta = nova_conta("comum", saldo=2000)
    t = client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 1000}).json()["transacao"]
    client.post(f"/transacoes/{t['id']}/estorno")
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 1000}).status_code == 201


# ---------------- Regra 5 ----------------
def test_fatura_atrasada_juros_e_bloqueio(client, nova_conta):
    conta = nova_conta("comum", saldo=5000)
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "limite": 3000}).json()
    r = client.post(f"/cartoes/{cartao['id']}/faturas", json={"mes_referencia": "2026-10", "valor": 1000})
    assert r.status_code == 201 and r.json()["vencimento"] == "2026-11-10"
    assert client.post(f"/cartoes/{cartao['id']}/faturas", json={"mes_referencia": "2026-10", "valor": 1}).status_code == 409
    f = client.get(f"/cartoes/{cartao['id']}/faturas").json()[0]
    # 17/11 -> 7 dias de atraso: 1000 * 8% * 7/30 = 18.67
    assert f["estado"] == "atrasada" and f["juros"] == 18.67
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "ativo"

    clock.fixar(AGORA + timedelta(days=4))  # 21/11 -> 11 dias de atraso
    resultado = client.post("/rotinas/processamento").json()
    assert resultado["cartoes_bloqueados"] == 1
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "bloqueado"
    f = client.get(f"/faturas/{f['id']}").json()
    assert f["juros"] == 29.33 and f["total_devido"] == 1029.33
    assert client.patch(f"/cartoes/{cartao['id']}", json={"estado": "ativo"}).status_code == 409

    r = client.post(f"/faturas/{f['id']}/pagamento")
    assert r.status_code == 200 and r.json()["estado"] == "paga" and r.json()["valor_pago"] == 1029.33
    assert saldo(client, conta["id"]) == 3940.67  # 5000 - 30,00 (tarifa mensal) - 1029,33
    assert client.post(f"/faturas/{f['id']}/pagamento").status_code == 409
    assert client.patch(f"/cartoes/{cartao['id']}", json={"estado": "ativo"}).status_code == 200


def test_juros_por_categoria(client, nova_conta):
    for categoria, juros in (("premium", 50.0), ("empresarial", 30.0)):
        conta = nova_conta(categoria)
        cartao = client.post("/cartoes", json={"conta_id": conta["id"], "limite": 3000}).json()
        client.post(
            f"/cartoes/{cartao['id']}/faturas",
            json={"mes_referencia": "2026-09", "valor": 1000, "vencimento": "2026-10-18"},
        )
        f = client.get(f"/cartoes/{cartao['id']}/faturas").json()[0]
        assert f["juros"] == juros  # 30 dias de atraso = 1 mes


def test_pagamento_sem_saldo(client, nova_conta):
    conta = nova_conta("comum", saldo=100)
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "limite": 3000}).json()
    f = client.post(f"/cartoes/{cartao['id']}/faturas", json={"mes_referencia": "2026-11", "valor": 500}).json()
    assert client.post(f"/faturas/{f['id']}/pagamento").status_code == 422


# ---------------- Regra 6 ----------------
def test_negativo_mais_de_30_dias_bloqueia_cliente_e_cartoes(client, novo_cliente, nova_conta):
    cli = novo_cliente("premium")
    conta = nova_conta(cliente_id=cli["id"], limite_credito=500)
    outra = nova_conta(cliente_id=cli["id"], saldo=100)
    c1 = client.post("/cartoes", json={"conta_id": conta["id"], "limite": 1000}).json()
    c2 = client.post("/cartoes", json={"conta_id": outra["id"], "limite": 1000}).json()
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 100})

    clock.fixar(AGORA + timedelta(days=30))
    assert client.post("/rotinas/processamento").json()["clientes_bloqueados"] == 0

    clock.fixar(AGORA + timedelta(days=30, seconds=1))
    r = client.post("/rotinas/processamento").json()
    assert r["clientes_bloqueados"] == 1 and r["cartoes_bloqueados"] == 2
    assert client.get(f"/clientes/{cli['id']}").json()["situacao"] == "bloqueado"
    assert client.get(f"/cartoes/{c1['id']}").json()["estado"] == "bloqueado"
    assert client.get(f"/cartoes/{c2['id']}").json()["estado"] == "bloqueado"
    assert client.patch(f"/clientes/{cli['id']}", json={"situacao": "ativo"}).status_code == 409
    rel = client.get("/relatorios/contas-saldo-negativo").json()
    assert rel[0]["conta_id"] == conta["id"] and rel[0]["dias_negativo"] == 30

    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 100})
    assert client.patch(f"/clientes/{cli['id']}", json={"situacao": "ativo"}).status_code == 200
    assert client.get("/relatorios/contas-saldo-negativo").json() == []


def test_regra_negativo_avaliada_na_operacao(client, nova_conta):
    conta = nova_conta("premium", limite_credito=500)
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 100})
    clock.fixar(AGORA + timedelta(days=31))
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 10}).status_code == 409
    assert client.get(f"/clientes/{conta['cliente_id']}").json()["situacao"] == "bloqueado"


def test_deposito_zera_negativo(client, nova_conta):
    conta = nova_conta("premium", limite_credito=500)
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 100})
    clock.fixar(AGORA + timedelta(days=20))
    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 100})
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 1})
    clock.fixar(AGORA + timedelta(days=40))
    assert client.post("/rotinas/processamento").json()["clientes_bloqueados"] == 0


# ---------------- Regra 7 ----------------
def test_encerramento_conta(client, nova_conta):
    conta = nova_conta("premium", saldo=100)
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "limite": 1000}).json()
    assert client.delete(f"/contas/{conta['id']}").status_code == 422  # saldo != 0
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 50})
    f = client.post(f"/cartoes/{cartao['id']}/faturas", json={"mes_referencia": "2026-11", "valor": 50}).json()
    assert client.delete(f"/contas/{conta['id']}").status_code == 422  # saldo 50
    client.post(f"/faturas/{f['id']}/pagamento")  # saldo -> 0
    assert saldo(client, conta["id"]) == 0
    f2 = client.post(f"/cartoes/{cartao['id']}/faturas", json={"mes_referencia": "2026-12", "valor": 0}).json()
    assert client.delete(f"/contas/{conta['id']}").status_code == 409  # fatura aberta
    client.post(f"/faturas/{f2['id']}/pagamento")
    r = client.delete(f"/contas/{conta['id']}")
    assert r.status_code == 200 and r.json()["estado"] == "encerrada"
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "cancelado"
    assert client.delete(f"/contas/{conta['id']}").status_code == 409
    assert client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 10}).status_code == 409


# ---------------- Tarifas mensais e relatorios ----------------
def test_tarifas_mensais_e_receita(client, nova_conta):
    comum = nova_conta("comum", saldo=100)
    premium = nova_conta("premium", saldo=100)
    empresarial = nova_conta("empresarial")  # sem saldo: tarifa fica pendente
    r = client.post("/rotinas/processamento").json()
    assert r["tarifas_mensais_geradas"] == 2
    assert client.post("/rotinas/processamento").json()["tarifas_mensais_geradas"] == 0  # idempotente
    assert saldo(client, comum["id"]) == 70
    assert saldo(client, premium["id"]) == 100
    t = client.get(f"/contas/{empresarial['id']}/tarifas").json()
    assert t[0]["valor"] == 120 and t[0]["estado"] == "pendente"
    client.post("/transacoes/deposito", json={"conta_id": empresarial["id"], "valor": 200})
    assert saldo(client, empresarial["id"]) == 80
    receita = {r["categoria"]: r["receita"] for r in client.get("/relatorios/receita-tarifas").json()}
    assert receita == {"comum": 30, "premium": 0, "empresarial": 120}


def test_relatorio_maior_movimentacao(client, nova_conta):
    a = nova_conta("premium", saldo=1000)
    b = nova_conta("premium", saldo=50)
    client.post("/transacoes/transferencia", json={"conta_origem_id": a["id"], "conta_destino_id": b["id"], "valor": 200})
    t = client.post("/transacoes/saque", json={"conta_id": b["id"], "valor": 10}).json()["transacao"]
    client.post(f"/transacoes/{t['id']}/estorno")
    r = client.get("/relatorios/clientes-maior-movimentacao", params={"inicio": "2026-11-01", "fim": "2026-11-30"})
    assert r.status_code == 200
    dados = r.json()
    assert [(d["cliente_id"], d["total_movimentado"], d["quantidade_transacoes"]) for d in dados] == [
        (a["cliente_id"], 1200, 2),
        (b["cliente_id"], 250, 2),
    ]
    assert client.get(
        "/relatorios/clientes-maior-movimentacao", params={"inicio": "2026-12-01", "fim": "2026-11-01"}
    ).status_code == 422
