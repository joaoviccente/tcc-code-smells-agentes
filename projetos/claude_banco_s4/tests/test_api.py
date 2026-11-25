from datetime import datetime, timedelta

from banco import clock

from .conftest import saldo


def avancar(**kw):
    clock.definir(clock.agora() + timedelta(**kw))


# ------------------------------------------------------------------ cadastros / validacao
def test_cliente_crud_e_validacoes(client, fabrica):
    c = fabrica.cliente()
    assert c["situacao"] == "ativo"
    assert client.post("/clientes", json={"nome": "X", "cpf": "123", "email": "a@b.com", "categoria": "comum"}).status_code == 422
    assert client.post("/clientes", json={"nome": "Xx", "cpf": "529.982.247-25", "email": "z@b.com",
                                          "categoria": "comum"}).status_code == 409  # CPF duplicado
    assert client.post("/clientes", json={"nome": "Xx", "cpf": "11144477735", "email": "nao-email",
                                          "categoria": "comum"}).status_code == 422
    assert client.post("/clientes", json={"nome": "Xx", "cpf": "11144477735", "email": "q@b.com",
                                          "categoria": "vip"}).status_code == 422
    assert client.get("/clientes/999").status_code == 404
    r = client.patch(f"/clientes/{c['id']}", json={"categoria": "premium"})
    assert r.status_code == 200 and r.json()["categoria"] == "premium"
    fabrica.conta(c["id"])
    assert client.delete(f"/clientes/{c['id']}").status_code == 409
    c2 = fabrica.cliente()
    assert client.delete(f"/clientes/{c2['id']}").status_code == 204


def test_valores_monetarios_validados(client, fabrica):
    conta = fabrica.conta(fabrica.cliente()["id"])
    for valor in (0, -10, 10.555, "abc"):
        r = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": valor})
        assert r.status_code == 422, valor
    assert client.post("/contas", json={"cliente_id": 1, "tipo": "poupanca", "limite_credito": 100}).status_code == 422


# ------------------------------------------------------------------ regras 1 e 2
def test_saque_limite_diario_comum_acumulado(client, fabrica):
    cli = fabrica.cliente("comum")
    a = fabrica.conta(cli["id"], saldo=5000)
    b = fabrica.conta(cli["id"], saldo=5000)
    assert client.post("/transacoes/saque", json={"conta_id": a["id"], "valor": 600}).status_code == 201
    # acumulado do cliente (inclusive em outra conta) nao pode passar de R$ 1.000,00
    r = client.post("/transacoes/saque", json={"conta_id": b["id"], "valor": 400.01})
    assert r.status_code == 422 and "Limite diario" in r.json()["detail"]
    assert client.post("/transacoes/saque", json={"conta_id": b["id"], "valor": 400}).status_code == 201
    avancar(days=1)
    assert client.post("/transacoes/saque", json={"conta_id": a["id"], "valor": 1000}).status_code == 201


def test_limites_por_categoria(client, fabrica):
    for cat, lim_saque, lim_transf in (("premium", 5000, 50000), ("empresarial", 20000, 200000)):
        cli = fabrica.cliente(cat)
        o = fabrica.conta(cli["id"], saldo=500000)
        d = fabrica.conta(fabrica.cliente()["id"])
        assert client.post("/transacoes/saque", json={"conta_id": o["id"], "valor": lim_saque + 0.01}).status_code == 422
        assert client.post("/transacoes/saque", json={"conta_id": o["id"], "valor": lim_saque}).status_code == 201
        t = {"conta_origem_id": o["id"], "conta_destino_id": d["id"]}
        assert client.post("/transacoes/transferencia", json={**t, "valor": lim_transf + 0.01}).status_code == 422
        assert client.post("/transacoes/transferencia", json={**t, "valor": lim_transf}).status_code == 201


def test_transferencia_limite_comum(client, fabrica):
    o = fabrica.conta(fabrica.cliente()["id"], saldo=10000)
    d = fabrica.conta(fabrica.cliente()["id"])
    t = {"conta_origem_id": o["id"], "conta_destino_id": d["id"]}
    assert client.post("/transacoes/transferencia", json={**t, "valor": 5000.01}).status_code == 422
    r = client.post("/transacoes/transferencia", json={**t, "valor": 5000})
    assert r.status_code == 201
    assert r.json()["saldos"] == {str(o["id"]): 5000.0, str(d["id"]): 5000.0}


def test_saldo_negativo_ate_limite_credito(client, fabrica):
    conta = fabrica.conta(fabrica.cliente()["id"], limite_credito=500, saldo=100)
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 600.01}).status_code == 422
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 600}).status_code == 201
    assert saldo(client, conta["id"]) == -500.0
    assert client.get(f"/contas/{conta['id']}").json()["negativo_desde"] is not None


def test_operacoes_bloqueadas_conta_ou_cliente(client, fabrica):
    cli = fabrica.cliente()
    conta = fabrica.conta(cli["id"], saldo=100)
    client.patch(f"/contas/{conta['id']}", json={"estado": "bloqueada"})
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 10}).status_code == 409
    client.patch(f"/contas/{conta['id']}", json={"estado": "ativa"})
    client.patch(f"/clientes/{cli['id']}", json={"situacao": "bloqueado"})
    assert client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 10}).status_code == 409
    outra = fabrica.conta(fabrica.cliente()["id"])
    r = client.post("/transacoes/transferencia",
                    json={"conta_origem_id": conta["id"], "conta_destino_id": outra["id"], "valor": 10})
    assert r.status_code == 409
    # deposito continua permitido para cliente bloqueado
    assert client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 10}).status_code == 201


# ------------------------------------------------------------------ regra 3
def test_franquia_e_tarifa_comum(client, fabrica):
    cli = fabrica.cliente("comum")
    a = fabrica.conta(cli["id"], saldo=1000)
    propria = fabrica.conta(cli["id"])
    terceiro = fabrica.conta(fabrica.cliente()["id"])
    # transferencia para conta do mesmo cliente: isenta e nao consome franquia
    r = client.post("/transacoes/transferencia",
                    json={"conta_origem_id": a["id"], "conta_destino_id": propria["id"], "valor": 10})
    assert r.json()["tarifa"]["estado"] == "isenta"
    assert r.json()["tarifa"]["tipo"] == "transferencia_mesmo_titular"
    estados = []
    for _ in range(4):
        r = client.post("/transacoes/transferencia",
                        json={"conta_origem_id": a["id"], "conta_destino_id": terceiro["id"], "valor": 10})
        estados.append((r.json()["tarifa"]["estado"], r.json()["tarifa"]["valor"]))
    assert estados == [("isenta", 0.0)] * 3 + [("cobrada", 2.5)]
    assert saldo(client, a["id"]) == 1000 - 50 - 2.5
    tarifas = client.get(f"/contas/{a['id']}/tarifas", params={"estado": "cobrada"}).json()
    assert len(tarifas) == 1


def test_premium_isento_ilimitado(client, fabrica):
    a = fabrica.conta(fabrica.cliente("premium")["id"], saldo=1000)
    for _ in range(10):
        r = client.post("/transacoes/saque", json={"conta_id": a["id"], "valor": 1})
        assert r.json()["tarifa"]["estado"] == "isenta"
    assert saldo(client, a["id"]) == 990.0


def test_operacao_nao_cabe_com_tarifa(client, fabrica):
    a = fabrica.conta(fabrica.cliente("comum")["id"], saldo=100)
    for _ in range(3):
        client.post("/transacoes/saque", json={"conta_id": a["id"], "valor": 1})
    r = client.post("/transacoes/saque", json={"conta_id": a["id"], "valor": 97})  # 97 + 2,50 > 97
    assert r.status_code == 422


# ------------------------------------------------------------------ regra 4
def test_estorno_transferencia(client, fabrica):
    o = fabrica.conta(fabrica.cliente()["id"], saldo=1000)
    d = fabrica.conta(fabrica.cliente()["id"])
    t = client.post("/transacoes/transferencia",
                    json={"conta_origem_id": o["id"], "conta_destino_id": d["id"], "valor": 300}).json()
    tid = t["transacao"]["id"]
    avancar(hours=23, minutes=59)
    r = client.post(f"/transacoes/{tid}/estorno")
    assert r.status_code == 201
    assert r.json()["transacao"]["tipo"] == "estorno"
    assert r.json()["transacao"]["transacao_original_id"] == tid
    assert saldo(client, o["id"]) == 1000.0 and saldo(client, d["id"]) == 0.0
    assert client.get(f"/transacoes/{tid}").json()["estado"] == "estornada"
    assert client.post(f"/transacoes/{tid}/estorno").status_code == 409
    extrato = client.get(f"/contas/{o['id']}/extrato").json()
    assert [i["efeito"] for i in extrato["itens"]] == [1000.0, -300.0, 300.0]


def test_estorno_fora_do_prazo(client, fabrica):
    a = fabrica.conta(fabrica.cliente()["id"])
    dep = client.post("/transacoes/deposito", json={"conta_id": a["id"], "valor": 50}).json()
    avancar(hours=24, seconds=1)
    r = client.post(f"/transacoes/{dep['transacao']['id']}/estorno")
    assert r.status_code == 422 and "24 horas" in r.json()["detail"]


def test_estorno_de_saque_libera_limite_diario(client, fabrica):
    a = fabrica.conta(fabrica.cliente()["id"], saldo=3000)
    s = client.post("/transacoes/saque", json={"conta_id": a["id"], "valor": 1000}).json()
    client.post(f"/transacoes/{s['transacao']['id']}/estorno")
    assert client.post("/transacoes/saque", json={"conta_id": a["id"], "valor": 1000}).status_code == 201


# ------------------------------------------------------------------ regra 5
def _cartao_com_compra(client, fabrica, categoria="comum", valor=1000):
    conta = fabrica.conta(fabrica.cliente(categoria)["id"])
    cartao = fabrica.cartao(conta["id"], limite=5000)
    r = client.post(f"/cartoes/{cartao['id']}/compras", json={"valor": valor})
    assert r.status_code == 201
    return conta, cartao, r.json()


def test_fatura_atraso_juros_e_bloqueio(client, fabrica):
    conta, cartao, fatura = _cartao_com_compra(client, fabrica, "comum", 1000)
    assert fatura["mes_referencia"] == "2026-03" and fatura["vencimento"] == "2026-04-10"
    assert client.post(f"/faturas/{fatura['id']}/pagamento", json={"valor": 1000}).status_code == 409  # aberta

    r = client.post("/rotinas/processamento-diario", params={"data_referencia": "2026-04-01"}).json()
    assert r["faturas_fechadas"] == 1
    # 10 dias de atraso: atrasada, juros 8% a.m. pro rata (1000 * 0.08 * 10/30 = 26.67), cartao ainda ativo
    r = client.post("/rotinas/processamento-diario", params={"data_referencia": "2026-04-20"}).json()
    assert r["faturas_atrasadas"] == 1 and r["cartoes_bloqueados_por_atraso"] == 0
    clock.definir(datetime(2026, 4, 20, 9))
    f = client.get(f"/faturas/{fatura['id']}").json()
    assert f["estado"] == "atrasada" and f["juros"] == 26.67
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "ativo"
    # 11 dias: cartao bloqueado
    r = client.post("/rotinas/processamento-diario", params={"data_referencia": "2026-04-21"}).json()
    assert r["cartoes_bloqueados_por_atraso"] == 1
    c = client.get(f"/cartoes/{cartao['id']}").json()
    assert c["estado"] == "bloqueado" and c["motivo_bloqueio"] == "fatura_atrasada"
    # pagamento exige valor + juros (30 dias => 8% => 80,00)
    clock.definir(datetime(2026, 5, 10, 9))
    assert client.post(f"/faturas/{fatura['id']}/pagamento", json={"valor": 1000}).status_code == 422
    r = client.post(f"/faturas/{fatura['id']}/pagamento", json={"valor": 1080})
    assert r.status_code == 200 and r.json()["estado"] == "paga"
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "ativo"


def test_juros_por_categoria(client, fabrica):
    esperados = {"premium": 50.0, "empresarial": 30.0}  # 30 dias de atraso sobre 1000
    faturas = {cat: _cartao_com_compra(client, fabrica, cat)[2] for cat in esperados}
    clock.definir(datetime(2026, 5, 10, 9))
    for cat, juros in esperados.items():
        assert client.get(f"/faturas/{faturas[cat]['id']}").json()["juros"] == juros


def test_limite_do_cartao(client, fabrica):
    conta = fabrica.conta(fabrica.cliente()["id"])
    cartao = fabrica.cartao(conta["id"], limite=100)
    assert client.post(f"/cartoes/{cartao['id']}/compras", json={"valor": 100}).status_code == 201
    assert client.post(f"/cartoes/{cartao['id']}/compras", json={"valor": 0.01}).status_code == 422


# ------------------------------------------------------------------ regra 6
def test_saldo_negativo_mais_de_30_dias(client, fabrica):
    cli = fabrica.cliente()
    conta = fabrica.conta(cli["id"], limite_credito=500)
    outra = fabrica.conta(cli["id"])
    c1 = fabrica.cartao(conta["id"])
    c2 = fabrica.cartao(outra["id"])
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 100})  # 10/03
    client.post("/rotinas/processamento-diario", params={"data_referencia": "2026-04-09"})  # 30 dias
    assert client.get(f"/clientes/{cli['id']}").json()["situacao"] == "ativo"
    neg = client.get("/relatorios/contas-saldo-negativo").json()
    assert neg[0]["conta_id"] == conta["id"]
    r = client.post("/rotinas/processamento-diario", params={"data_referencia": "2026-04-10"}).json()
    assert r["clientes_bloqueados_por_saldo_negativo"] == 1 and r["cartoes_bloqueados_por_cliente"] == 2
    assert client.get(f"/clientes/{cli['id']}").json()["situacao"] == "bloqueado"
    for c in (c1, c2):
        assert client.get(f"/cartoes/{c['id']}").json()["estado"] == "bloqueado"


def test_saldo_regulariza_reinicia_contagem(client, fabrica):
    cli = fabrica.cliente()
    conta = fabrica.conta(cli["id"], limite_credito=500)
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 100})
    clock.definir(datetime(2026, 3, 25, 10))
    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 100})
    assert client.get(f"/contas/{conta['id']}").json()["negativo_desde"] is None
    client.post("/rotinas/processamento-diario", params={"data_referencia": "2026-04-20"})
    assert client.get(f"/clientes/{cli['id']}").json()["situacao"] == "ativo"


# ------------------------------------------------------------------ regra 7
def test_encerramento_conta(client, fabrica):
    conta, cartao, fatura = _cartao_com_compra(client, fabrica, valor=200)
    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 10})
    r = client.delete(f"/contas/{conta['id']}")
    assert r.status_code == 409 and "saldo zero" in r.json()["detail"]
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 10})
    r = client.delete(f"/contas/{conta['id']}")
    assert r.status_code == 409 and "faturas" in r.json()["detail"]
    clock.definir(datetime(2026, 4, 2, 10))
    client.post(f"/faturas/{fatura['id']}/pagamento", json={"valor": 200})
    r = client.delete(f"/contas/{conta['id']}")
    assert r.status_code == 200 and r.json()["estado"] == "encerrada"
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "cancelado"
    assert client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 1}).status_code == 409


# ------------------------------------------------------------------ tarifas mensais e relatorios
def test_tarifa_mensal_e_receita(client, fabrica):
    contas = {cat: fabrica.conta(fabrica.cliente(cat)["id"], saldo=1000) for cat in ("comum", "premium", "empresarial")}
    r = client.post("/rotinas/processamento-diario", params={"data_referencia": "2026-04-01"}).json()
    assert r["tarifas_mensais_geradas"] == 3
    # idempotente
    assert client.post("/rotinas/processamento-diario",
                       params={"data_referencia": "2026-04-02"}).json()["tarifas_mensais_geradas"] == 0
    assert saldo(client, contas["comum"]["id"]) == 970.0
    assert saldo(client, contas["premium"]["id"]) == 1000.0
    assert saldo(client, contas["empresarial"]["id"]) == 880.0
    receita = {x["categoria"]: x["receita"] for x in client.get("/relatorios/receita-tarifas").json()}
    assert receita == {"comum": 30.0, "premium": 0.0, "empresarial": 120.0}


def test_tarifa_mensal_pendente_sem_saldo(client, fabrica):
    conta = fabrica.conta(fabrica.cliente("comum")["id"])
    client.post("/rotinas/processamento-diario", params={"data_referencia": "2026-04-01"})
    t = client.get(f"/contas/{conta['id']}/tarifas", params={"tipo": "mensal"}).json()
    assert t[0]["estado"] == "pendente"
    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 50})
    r = client.post("/rotinas/processamento-diario", params={"data_referencia": "2026-04-02"}).json()
    assert r["tarifas_pendentes_cobradas"] == 1
    assert saldo(client, conta["id"]) == 20.0


def test_relatorio_maior_movimentacao(client, fabrica):
    c1, c2 = fabrica.cliente(), fabrica.cliente()
    a = fabrica.conta(c1["id"], saldo=100)
    b = fabrica.conta(c2["id"], saldo=500)
    client.post("/transacoes/transferencia", json={"conta_origem_id": b["id"], "conta_destino_id": a["id"], "valor": 50})
    r = client.get("/relatorios/clientes-maior-movimentacao",
                   params={"inicio": "2026-03-01T00:00:00", "fim": "2026-03-31T23:59:59"}).json()
    assert [(x["cliente_id"], x["total_movimentado"]) for x in r] == [(c2["id"], 550.0), (c1["id"], 150.0)]
    assert client.get("/relatorios/clientes-maior-movimentacao",
                      params={"inicio": "2026-04-01T00:00:00", "fim": "2026-03-01T00:00:00"}).status_code == 422
