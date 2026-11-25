from decimal import Decimal

D = Decimal


def saldo(client, conta_id):
    return D(client.get(f"/contas/{conta_id}").json()["saldo"])


def saque(client, conta_id, valor):
    return client.post("/transacoes/saque", json={"conta_id": conta_id, "valor": valor})


def transf(client, o, d, valor):
    return client.post("/transacoes/transferencia",
                       json={"conta_origem_id": o, "conta_destino_id": d, "valor": valor})


# ----------------------------------------------------------------- cadastro

def test_crud_cliente_e_validacoes(client, novo_cliente):
    c = novo_cliente("premium")
    assert c["situacao"] == "ativo"
    # CPF invalido / e-mail invalido / categoria invalida / campo extra
    assert client.post("/clientes", json={"nome": "X Y", "cpf": "12345678900", "email": "a@b.com",
                                          "categoria": "comum"}).status_code == 422
    assert client.post("/clientes", json={"nome": "X Y", "cpf": "529.982.247-25", "email": "ab.com",
                                          "categoria": "comum"}).status_code == 422
    assert client.post("/clientes", json={"nome": "X Y", "cpf": "529.982.247-25", "email": "a@b.com",
                                          "categoria": "vip"}).status_code == 422
    # duplicidade de CPF
    r = client.post("/clientes", json={"nome": "X Y", "cpf": c["cpf"], "email": "z@b.com",
                                       "categoria": "comum"})
    assert r.status_code == 409
    r = client.patch(f"/clientes/{c['id']}", json={"categoria": "empresarial"})
    assert r.status_code == 200 and r.json()["categoria"] == "empresarial"
    assert client.get("/clientes/9999").status_code == 404
    assert client.delete(f"/clientes/{c['id']}").status_code == 204
    assert client.get(f"/clientes/{c['id']}").status_code == 404


def test_cliente_com_conta_nao_pode_ser_removido(client, nova_conta):
    conta = nova_conta()
    assert client.delete(f"/clientes/{conta['cliente_id']}").status_code == 409


def test_poupanca_sem_limite_de_credito(client, novo_cliente):
    c = novo_cliente()
    r = client.post("/contas", json={"cliente_id": c["id"], "tipo": "poupanca",
                                     "limite_credito": "100"})
    assert r.status_code == 422


def test_valor_com_mais_de_duas_casas_e_negativo(client, nova_conta):
    conta = nova_conta()
    assert client.post("/transacoes/deposito",
                       json={"conta_id": conta["id"], "valor": "10.001"}).status_code == 422
    assert client.post("/transacoes/deposito",
                       json={"conta_id": conta["id"], "valor": "-5"}).status_code == 422


# ------------------------------------------------------------ regras 1 e 2

def test_limite_diario_saque_comum_acumulado(client, nova_conta, relogio):
    conta = nova_conta("comum", saldo="5000")
    assert saque(client, conta["id"], "600.00").status_code == 201
    r = saque(client, conta["id"], "400.01")
    assert r.status_code == 422 and "Limite diario" in r.json()["detail"]
    assert saque(client, conta["id"], "400.00").status_code == 201
    relogio.avancar(days=1)
    assert saque(client, conta["id"], "1000.00").status_code == 201


def test_limite_diario_saque_por_categoria(client, nova_conta):
    p = nova_conta("premium", saldo="30000")
    assert saque(client, p["id"], "5000.00").status_code == 201
    assert saque(client, p["id"], "0.01").status_code == 422
    e = nova_conta("empresarial", saldo="30000")
    assert saque(client, e["id"], "20000.00").status_code == 201
    assert saque(client, e["id"], "0.01").status_code == 422


def test_limite_diario_saque_e_por_cliente(client, nova_conta):
    c1 = nova_conta("comum", saldo="1000")
    c2 = nova_conta(cliente_id=c1["cliente_id"], saldo="1000")
    assert saque(client, c1["id"], "700").status_code == 201
    assert saque(client, c2["id"], "301").status_code == 422


def test_limite_por_transferencia(client, nova_conta):
    o = nova_conta("comum", saldo="10000")
    d = nova_conta("comum")
    assert transf(client, o["id"], d["id"], "5000.01").status_code == 422
    assert transf(client, o["id"], d["id"], "5000.00").status_code == 201
    p = nova_conta("premium", saldo="60000")
    assert transf(client, p["id"], d["id"], "50000.01").status_code == 422
    assert transf(client, p["id"], d["id"], "50000.00").status_code == 201
    e = nova_conta("empresarial", saldo="250000")
    assert transf(client, e["id"], d["id"], "200000.01").status_code == 422
    assert transf(client, e["id"], d["id"], "200000.00").status_code == 201


def test_saldo_negativo_ate_limite_de_credito(client, nova_conta):
    conta = nova_conta("premium", saldo="100", limite_credito="500")
    assert saque(client, conta["id"], "600.01").status_code == 422
    r = saque(client, conta["id"], "600.00")
    assert r.status_code == 201
    assert D(r.json()["saldo_conta"]) == D("-500.00")
    assert client.get(f"/contas/{conta['id']}").json()["negativo_desde"] is not None
    assert saque(client, conta["id"], "0.01").status_code == 422


def test_operacoes_exigem_conta_e_cliente_ativos(client, nova_conta):
    conta = nova_conta(saldo="100")
    client.patch(f"/contas/{conta['id']}", json={"estado": "bloqueada"})
    assert saque(client, conta["id"], "10").status_code == 409
    client.patch(f"/contas/{conta['id']}", json={"estado": "ativa"})
    client.patch(f"/clientes/{conta['cliente_id']}", json={"situacao": "bloqueado"})
    assert saque(client, conta["id"], "10").status_code == 409
    outra = nova_conta()
    assert transf(client, conta["id"], outra["id"], "10").status_code == 409


# ---------------------------------------------------------------- regra 3

def test_franquia_e_tarifa_comum(client, nova_conta):
    conta = nova_conta("comum", saldo="1000")
    for _ in range(3):
        r = saque(client, conta["id"], "10")
        assert r.json()["tarifa"]["estado"] == "isenta"
    r = saque(client, conta["id"], "10")
    assert r.json()["tarifa"]["estado"] == "cobrada"
    assert D(r.json()["tarifa"]["valor"]) == D("5.00")
    assert saldo(client, conta["id"]) == D("1000") - D("40") - D("5")


def test_premium_isencao_ilimitada(client, nova_conta):
    conta = nova_conta("premium", saldo="1000")
    for _ in range(10):
        assert saque(client, conta["id"], "1").json()["tarifa"]["estado"] == "isenta"
    assert saldo(client, conta["id"]) == D("990.00")


def test_transferencia_mesmo_cliente_isenta_sem_consumir_franquia(client, nova_conta):
    a = nova_conta("comum", saldo="1000")
    b = nova_conta(cliente_id=a["cliente_id"])
    for _ in range(5):
        r = transf(client, a["id"], b["id"], "10")
        assert r.status_code == 201 and r.json()["tarifa"] is None
    terceiro = nova_conta()
    for i in range(3):
        assert transf(client, a["id"], terceiro["id"], "10").json()["tarifa"]["estado"] == "isenta"
    assert transf(client, a["id"], terceiro["id"], "10").json()["tarifa"]["estado"] == "cobrada"


def test_tarifas_mensais(client, nova_conta):
    c = nova_conta("comum", saldo="100")
    p = nova_conta("premium")
    e = nova_conta("empresarial")  # sem saldo -> pendente
    r = client.post("/processamentos/tarifas-mensais", json={"mes_referencia": "2026-11"})
    assert r.status_code == 200
    assert r.json() == {"mes_referencia": "2026-11", "geradas": 3, "cobradas": 1, "isentas": 1,
                        "pendentes": 1, "ja_existentes": 0}
    assert saldo(client, c["id"]) == D("70.00")
    t = client.get(f"/contas/{e['id']}/tarifas").json()
    assert t[0]["estado"] == "pendente" and D(t[0]["valor"]) == D("120.00")
    assert client.get(f"/contas/{p['id']}/tarifas").json()[0]["estado"] == "isenta"
    # idempotente
    r = client.post("/processamentos/tarifas-mensais", json={"mes_referencia": "2026-11"})
    assert r.json()["ja_existentes"] == 3
    # deposito cobra a pendente
    client.post("/transacoes/deposito", json={"conta_id": e["id"], "valor": "200"})
    assert saldo(client, e["id"]) == D("80.00")
    rec = client.get("/relatorios/receita-tarifas").json()
    por_cat = {x["categoria"]: x for x in rec["categorias"]}
    assert D(por_cat["comum"]["receita_total"]) == D("30.00")
    assert D(por_cat["empresarial"]["receita_mensalidades"]) == D("120.00")
    assert D(por_cat["premium"]["receita_total"]) == D("0")
    assert D(rec["receita_total"]) == D("150.00")


# ---------------------------------------------------------------- regra 4

def test_estorno_transferencia(client, nova_conta, relogio):
    a = nova_conta(saldo="1000")
    b = nova_conta()
    t = transf(client, a["id"], b["id"], "300").json()["transacao"]
    r = client.post(f"/transacoes/{t['id']}/estorno")
    assert r.status_code == 201
    assert r.json()["estorno"]["tipo"] == "estorno"
    assert r.json()["transacao_original"]["estado"] == "estornada"
    assert saldo(client, a["id"]) == D("1000")
    assert saldo(client, b["id"]) == D("0")
    assert client.post(f"/transacoes/{t['id']}/estorno").status_code == 409
    est_id = r.json()["estorno"]["id"]
    assert client.post(f"/transacoes/{est_id}/estorno").status_code == 409
    ext = client.get(f"/contas/{a['id']}/extrato").json()
    naturezas = [(l["tipo"], l["natureza"]) for l in ext["lancamentos"]]
    assert naturezas == [("deposito", "credito"), ("transferencia", "debito"),
                         ("estorno", "credito")]


def test_estorno_prazo_24h(client, nova_conta, relogio):
    conta = nova_conta(saldo="100")
    t = saque(client, conta["id"], "50").json()["transacao"]
    relogio.avancar(hours=24, seconds=1)
    assert client.post(f"/transacoes/{t['id']}/estorno").status_code == 422
    t2 = saque(client, conta["id"], "10").json()["transacao"]
    relogio.avancar(hours=24)
    assert client.post(f"/transacoes/{t2['id']}/estorno").status_code == 201


def test_estorno_saque_libera_limite_diario(client, nova_conta):
    conta = nova_conta(saldo="2000")
    t = saque(client, conta["id"], "1000").json()["transacao"]
    assert saque(client, conta["id"], "1").status_code == 422
    client.post(f"/transacoes/{t['id']}/estorno")
    assert saque(client, conta["id"], "1000").status_code == 201


# ---------------------------------------------------------------- regra 5

def _cartao_com_fatura(client, nova_conta, categoria, valor="1000.00"):
    conta = nova_conta(categoria)
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "limite": "5000"}).json()
    f = client.post(f"/cartoes/{cartao['id']}/faturas",
                    json={"mes_referencia": "2026-11", "valor": valor,
                          "data_vencimento": "2026-12-10"})
    assert f.status_code == 201, f.text
    return conta, cartao, f.json()


def test_fatura_atrasada_juros_e_bloqueio(client, nova_conta, relogio):
    from datetime import datetime
    _, cartao, f = _cartao_com_fatura(client, nova_conta, "comum")
    relogio.atual = datetime(2026, 12, 20, 9, 0)  # 10 dias de atraso
    r = client.post("/processamentos/diario").json()
    assert r["faturas_marcadas_atrasadas"] == 1 and r["cartoes_bloqueados_por_atraso"] == 0
    fat = client.get(f"/faturas/{f['id']}").json()
    assert fat["estado"] == "atrasada"
    # 1000 * 8% * 10/30 = 26.67
    assert D(fat["juros"]) == D("26.67") and D(fat["valor_total"]) == D("1026.67")
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "ativo"
    relogio.atual = datetime(2026, 12, 21, 9, 0)  # 11 dias
    r = client.post("/processamentos/diario").json()
    assert r["cartoes_bloqueados_por_atraso"] == 1
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "bloqueado"
    # pagamento com valor errado e certo (1000 * 8% * 11/30 = 29.33)
    assert client.post(f"/faturas/{f['id']}/pagamento", json={"valor": "1000"}).status_code == 422
    p = client.post(f"/faturas/{f['id']}/pagamento", json={"valor": "1029.33"})
    assert p.status_code == 200 and p.json()["estado"] == "paga"
    assert client.post(f"/faturas/{f['id']}/pagamento", json={"valor": "1029.33"}).status_code == 409


def test_juros_por_categoria(client, nova_conta, relogio):
    from datetime import datetime
    _, c1, f1 = _cartao_com_fatura(client, nova_conta, "premium")
    _, c2, f2 = _cartao_com_fatura(client, nova_conta, "empresarial")
    relogio.atual = datetime(2027, 1, 9, 9, 0)  # 30 dias de atraso
    assert D(client.get(f"/faturas/{f1['id']}").json()["juros"]) == D("50.00")
    assert D(client.get(f"/faturas/{f2['id']}").json()["juros"]) == D("30.00")


# ---------------------------------------------------------------- regra 6

def test_saldo_negativo_30_dias_bloqueia_cliente_e_cartoes(client, nova_conta, relogio):
    conta = nova_conta("comum", limite_credito="500")
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "limite": "1000"}).json()
    assert saque(client, conta["id"], "100").status_code == 201
    relogio.avancar(days=30)
    r = client.post("/processamentos/diario").json()
    assert r["clientes_bloqueados_saldo_negativo"] == 0
    relogio.avancar(days=1)
    r = client.post("/processamentos/diario").json()
    assert r["clientes_bloqueados_saldo_negativo"] == 1
    assert client.get(f"/clientes/{conta['cliente_id']}").json()["situacao"] == "bloqueado"
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "bloqueado"
    neg = client.get("/relatorios/contas-saldo-negativo").json()
    assert neg[0]["conta_id"] == conta["id"] and neg[0]["dias_negativo"] == 31
    # nao pode desbloquear enquanto negativo
    assert client.patch(f"/clientes/{conta['cliente_id']}",
                        json={"situacao": "ativo"}).status_code == 409


def test_regra_6_aplicada_sob_demanda_no_saque(client, nova_conta, relogio):
    conta = nova_conta("comum", limite_credito="500")
    saque(client, conta["id"], "100")
    relogio.avancar(days=31)
    assert saque(client, conta["id"], "10").status_code == 409
    assert client.get(f"/clientes/{conta['cliente_id']}").json()["situacao"] == "bloqueado"


# ---------------------------------------------------------------- regra 7

def test_encerramento_de_conta(client, nova_conta):
    conta = nova_conta(saldo="100")
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "limite": "1000"}).json()
    assert client.delete(f"/contas/{conta['id']}").status_code == 409  # saldo != 0
    saque(client, conta["id"], "100")
    f = client.post(f"/cartoes/{cartao['id']}/faturas",
                    json={"mes_referencia": "2026-11", "valor": "50"}).json()
    assert client.delete(f"/contas/{conta['id']}").status_code == 409  # fatura aberta
    client.post(f"/faturas/{f['id']}/pagamento", json={"valor": "50.00"})
    r = client.delete(f"/contas/{conta['id']}")
    assert r.status_code == 200 and r.json()["estado"] == "encerrada"
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "cancelado"
    assert client.post("/transacoes/deposito",
                       json={"conta_id": conta["id"], "valor": "1"}).status_code == 409


# ---------------------------------------------------------------- relatorios

def test_relatorio_maior_movimentacao(client, nova_conta):
    a = nova_conta("premium", saldo="5000")
    b = nova_conta("comum", saldo="10")
    transf(client, a["id"], b["id"], "1000")
    r = client.get("/relatorios/clientes-maior-movimentacao",
                   params={"inicio": "2026-11-01", "fim": "2026-11-30"})
    assert r.status_code == 200
    dados = r.json()
    assert dados[0]["cliente_id"] == a["cliente_id"]
    assert D(dados[0]["total_movimentado"]) == D("6000.00")
    assert D(dados[1]["total_movimentado"]) == D("1010.00")
    assert client.get("/relatorios/clientes-maior-movimentacao",
                      params={"inicio": "2026-12-01", "fim": "2026-11-01"}).status_code == 422
