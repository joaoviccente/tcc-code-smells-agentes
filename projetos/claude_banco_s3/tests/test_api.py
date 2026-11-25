from datetime import timedelta


def saldo(client, conta_id):
    return client.get(f"/contas/{conta_id}").json()["saldo"]


def saque(client, conta_id, valor):
    return client.post("/transacoes/saque", json={"conta_id": conta_id, "valor": valor})


def transf(client, origem, destino, valor):
    return client.post("/transacoes/transferencia",
                       json={"conta_origem_id": origem, "conta_destino_id": destino, "valor": valor})


# ---------------- validacao / CRUD ----------------
def test_validacao_cliente(client, novo_cliente):
    base = {"nome": "Maria Silva", "email": "maria@example.com"}
    assert client.post("/clientes", json={**base, "cpf": "12345678900"}).status_code == 422
    assert client.post("/clientes", json={**base, "cpf": "52998224725", "email": "x"}).status_code == 422
    assert client.post("/clientes", json={**base, "cpf": "52998224725", "categoria": "vip"}).status_code == 422
    r = client.post("/clientes", json={**base, "cpf": "529.982.247-25"})
    assert r.status_code == 201 and r.json()["cpf"] == "52998224725"
    assert client.post("/clientes", json={**base, "cpf": "52998224725"}).status_code == 409
    assert client.get("/clientes/999").status_code == 404


def test_crud_basico(client, novo_cliente, nova_conta):
    c = novo_cliente()
    r = client.patch(f"/clientes/{c['id']}", json={"categoria": "premium"})
    assert r.status_code == 200 and r.json()["categoria"] == "premium"
    conta = nova_conta(c["id"], limite="100.00")
    assert conta["saldo"] == 0 and conta["estado"] == "ativa"
    assert client.delete(f"/clientes/{c['id']}").status_code == 409
    r = client.post("/cartoes", json={"conta_id": conta["id"], "limite": "1500.00"})
    assert r.status_code == 201 and len(r.json()["numero"]) == 16
    assert client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": -5}).status_code == 422
    assert client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": "1.001"}).status_code == 422


# ---------------- regras 1 e 2 ----------------
def test_limite_diario_saque_comum(client, novo_cliente, nova_conta, relogio):
    c = novo_cliente("comum")
    conta = nova_conta(c["id"], saldo="5000.00")
    assert saque(client, conta["id"], "600.00").status_code == 201
    r = saque(client, conta["id"], "400.01")
    assert r.status_code == 422 and r.json()["erro"] == "limite_diario_saque_excedido"
    assert saque(client, conta["id"], "400.00").status_code == 201  # total exatamente 1000,00
    relogio.avancar(days=1)
    assert saque(client, conta["id"], "1000.00").status_code == 201


def test_limite_diario_acumula_entre_contas_do_cliente(client, novo_cliente, nova_conta):
    c = novo_cliente("comum")
    a = nova_conta(c["id"], saldo="2000.00")
    b = nova_conta(c["id"], saldo="2000.00")
    assert saque(client, a["id"], "700.00").status_code == 201
    assert saque(client, b["id"], "300.01").status_code == 422


def test_limites_por_categoria(client, novo_cliente, nova_conta):
    p = novo_cliente("premium")
    e = novo_cliente("empresarial")
    cp = nova_conta(p["id"], saldo="100000.00")
    ce = nova_conta(e["id"], saldo="300000.00")
    assert saque(client, cp["id"], "5000.00").status_code == 201
    assert saque(client, cp["id"], "0.01").status_code == 422
    assert saque(client, ce["id"], "20000.00").status_code == 201
    assert saque(client, ce["id"], "0.01").status_code == 422
    assert transf(client, cp["id"], ce["id"], "50000.01").status_code == 422
    assert transf(client, cp["id"], ce["id"], "50000.00").status_code == 201
    assert transf(client, ce["id"], cp["id"], "200000.01").status_code == 422
    assert transf(client, ce["id"], cp["id"], "200000.00").status_code == 201


def test_limite_transferencia_comum(client, novo_cliente, nova_conta):
    c = novo_cliente("comum")
    a = nova_conta(c["id"], saldo="10000.00")
    b = nova_conta(c["id"])
    r = transf(client, a["id"], b["id"], "5000.01")
    assert r.status_code == 422 and r.json()["erro"] == "limite_transferencia_excedido"
    assert transf(client, a["id"], b["id"], "5000.00").status_code == 201


def test_saldo_negativo_ate_limite_credito(client, novo_cliente, nova_conta):
    c = novo_cliente("premium")
    conta = nova_conta(c["id"], limite="500.00", saldo="100.00")
    assert saque(client, conta["id"], "600.01").status_code == 422
    assert saque(client, conta["id"], "600.00").status_code == 201
    assert saldo(client, conta["id"]) == -500.0


def test_conta_bloqueada_e_cliente_bloqueado(client, novo_cliente, nova_conta):
    c = novo_cliente()
    conta = nova_conta(c["id"], saldo="100.00")
    client.patch(f"/contas/{conta['id']}", json={"estado": "bloqueada"})
    assert saque(client, conta["id"], "10.00").status_code == 409
    client.patch(f"/contas/{conta['id']}", json={"estado": "ativa"})
    client.patch(f"/clientes/{c['id']}", json={"situacao": "bloqueado"})
    r = saque(client, conta["id"], "10.00")
    assert r.status_code == 409 and r.json()["erro"] == "cliente_bloqueado"


# ---------------- regra 3: tarifas ----------------
def test_franquia_e_tarifa_comum(client, novo_cliente, nova_conta):
    a = novo_cliente("comum")
    b = novo_cliente("comum")
    ca = nova_conta(a["id"], saldo="1000.00")
    ca2 = nova_conta(a["id"])
    cb = nova_conta(b["id"])
    # transferencia entre contas do mesmo cliente: isenta e nao consome franquia
    r = transf(client, ca["id"], ca2["id"], "10.00")
    assert r.json()["tarifa"] is None
    for _ in range(3):
        assert transf(client, ca["id"], cb["id"], "10.00").json()["tarifa"]["estado"] == "isenta"
    r = transf(client, ca["id"], cb["id"], "10.00").json()
    assert r["tarifa"]["estado"] == "cobrada" and r["tarifa"]["valor"] == 2.5
    assert saldo(client, ca["id"]) == 1000 - 50 - 2.5
    tarifas = client.get(f"/contas/{ca['id']}/tarifas").json()
    assert [t["estado"] for t in tarifas] == ["isenta"] * 3 + ["cobrada"]


def test_premium_isencao_ilimitada(client, novo_cliente, nova_conta):
    a = novo_cliente("premium")
    b = novo_cliente("comum")
    ca = nova_conta(a["id"], saldo="1000.00")
    cb = nova_conta(b["id"])
    for _ in range(10):
        assert transf(client, ca["id"], cb["id"], "1.00").json()["tarifa"]["estado"] == "isenta"


def test_tarifa_mensal(client, novo_cliente, nova_conta):
    contas = {cat: nova_conta(novo_cliente(cat)["id"], saldo="500.00") for cat in ("comum", "premium", "empresarial")}
    r = client.post("/rotinas/tarifas-mensais", params={"competencia": "2026-11"}).json()
    assert r["tarifas_geradas"] == 3 and r["isentas"] == 1 and r["cobradas"] == 2
    assert saldo(client, contas["comum"]["id"]) == 470.0
    assert saldo(client, contas["premium"]["id"]) == 500.0
    assert saldo(client, contas["empresarial"]["id"]) == 380.0
    # idempotente
    assert client.post("/rotinas/tarifas-mensais", params={"competencia": "2026-11"}).json()["tarifas_geradas"] == 0
    rec = client.get("/relatorios/receita-tarifas", params={"data_inicio": "2026-11-01", "data_fim": "2026-11-30"}).json()
    por = {x["categoria"]: x["receita"] for x in rec["por_categoria"]}
    assert por == {"comum": 30.0, "premium": 0.0, "empresarial": 120.0} and rec["total"] == 150.0


def test_tarifa_mensal_pendente_cobrada_no_deposito(client, novo_cliente, nova_conta):
    conta = nova_conta(novo_cliente("comum")["id"])
    r = client.post("/rotinas/tarifas-mensais", params={"competencia": "2026-11"}).json()
    assert r["pendentes"] == 1
    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": "100.00"})
    assert saldo(client, conta["id"]) == 70.0
    assert client.get(f"/contas/{conta['id']}/tarifas").json()[0]["estado"] == "cobrada"


# ---------------- regra 4: estorno ----------------
def test_estorno_transferencia(client, novo_cliente, nova_conta, relogio):
    a, b = novo_cliente(), novo_cliente()
    ca = nova_conta(a["id"], saldo="1000.00")
    cb = nova_conta(b["id"])
    t = transf(client, ca["id"], cb["id"], "300.00").json()["transacao"]
    relogio.avancar(hours=23, minutes=59)
    r = client.post(f"/transacoes/{t['id']}/estorno", json={"motivo": "erro"})
    assert r.status_code == 201
    assert r.json()["transacao"]["tipo"] == "estorno"
    assert r.json()["transacao"]["transacao_original_id"] == t["id"]
    assert saldo(client, ca["id"]) == 1000.0 and saldo(client, cb["id"]) == 0.0
    assert client.get(f"/transacoes/{t['id']}").json()["estado"] == "estornada"
    assert client.post(f"/transacoes/{t['id']}/estorno").status_code == 409
    ext = client.get(f"/contas/{cb['id']}/extrato").json()
    assert [(l["tipo"], l["natureza"]) for l in ext["lancamentos"]] == [("transferencia", "credito"), ("estorno", "debito")]


def test_estorno_fora_do_prazo(client, novo_cliente, nova_conta, relogio):
    conta = nova_conta(novo_cliente()["id"])
    t = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": "50.00"}).json()["transacao"]
    relogio.avancar(hours=24, seconds=1)
    r = client.post(f"/transacoes/{t['id']}/estorno")
    assert r.status_code == 422 and r.json()["erro"] == "prazo_estorno_expirado"


def test_estorno_saque_libera_limite_diario(client, novo_cliente, nova_conta):
    conta = nova_conta(novo_cliente()["id"], saldo="2000.00")
    t = saque(client, conta["id"], "1000.00").json()["transacao"]
    assert client.post(f"/transacoes/{t['id']}/estorno").status_code == 201
    assert saque(client, conta["id"], "1000.00").status_code == 201


# ---------------- regra 5: faturas ----------------
def _cartao_com_fatura(client, novo_cliente, nova_conta, categoria="comum"):
    conta = nova_conta(novo_cliente(categoria)["id"])
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "limite": "5000.00"}).json()
    f = client.post(f"/cartoes/{cartao['id']}/faturas",
                    json={"mes_referencia": "2026-11", "valor": "1000.00", "data_vencimento": "2026-11-20"}).json()
    return conta, cartao, f


def test_fatura_atraso_juros_e_bloqueio(client, novo_cliente, nova_conta, relogio):
    conta, cartao, f = _cartao_com_fatura(client, novo_cliente, nova_conta, "comum")
    relogio.avancar(days=2)  # 20/11 = dia do vencimento: ainda nao atrasada
    assert client.get(f"/cartoes/{cartao['id']}/faturas").json()[0]["estado"] == "aberta"
    relogio.avancar(days=10)  # 30/11: 10 dias de atraso
    fat = client.get(f"/cartoes/{cartao['id']}/faturas").json()[0]
    assert fat["estado"] == "atrasada"
    assert fat["juros"] == 26.67  # 1000 * 8% * 10/30
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "ativo"
    relogio.avancar(days=1)  # 11 dias de atraso
    r = client.post("/rotinas/diaria").json()
    assert r["cartoes_bloqueados_por_atraso"] == 1
    c = client.get(f"/cartoes/{cartao['id']}").json()
    assert c["estado"] == "bloqueado" and c["motivo_bloqueio"] == "fatura_atrasada"
    fat = client.get(f"/faturas/{f['id']}").json()
    assert client.post(f"/faturas/{f['id']}/pagamento", json={"valor": "1000.00"}).status_code == 422
    r = client.post(f"/faturas/{f['id']}/pagamento", json={"valor": fat["valor"]})
    assert r.status_code == 200 and r.json()["estado"] == "paga"
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "ativo"
    assert client.post(f"/faturas/{f['id']}/pagamento", json={"valor": fat["valor"]}).status_code == 409


def test_juros_por_categoria(client, novo_cliente, nova_conta, relogio):
    _, cp, _ = _cartao_com_fatura(client, novo_cliente, nova_conta, "premium")
    _, ce, _ = _cartao_com_fatura(client, novo_cliente, nova_conta, "empresarial")
    relogio.avancar(days=32)  # 30 dias de atraso = 1 mes
    assert client.get(f"/cartoes/{cp['id']}/faturas").json()[0]["juros"] == 50.0
    assert client.get(f"/cartoes/{ce['id']}/faturas").json()[0]["juros"] == 30.0


# ---------------- regra 6 ----------------
def test_saldo_negativo_30_dias_bloqueia_cliente_e_cartoes(client, novo_cliente, nova_conta, relogio):
    c = novo_cliente()
    conta = nova_conta(c["id"], limite="1000.00")
    outra = nova_conta(c["id"])
    k1 = client.post("/cartoes", json={"conta_id": conta["id"], "limite": "100.00"}).json()
    k2 = client.post("/cartoes", json={"conta_id": outra["id"], "limite": "100.00"}).json()
    assert saque(client, conta["id"], "100.00").status_code == 201
    relogio.avancar(days=30)
    assert client.post("/rotinas/diaria").json()["clientes_bloqueados_por_saldo_negativo"] == 0
    relogio.avancar(seconds=1)
    r = saque(client, conta["id"], "10.00")  # verificacao preguicosa na operacao
    assert r.status_code == 409 and r.json()["erro"] == "cliente_bloqueado"
    assert client.get(f"/clientes/{c['id']}").json()["situacao"] == "bloqueado"
    assert client.get(f"/cartoes/{k1['id']}").json()["estado"] == "bloqueado"
    assert client.get(f"/cartoes/{k2['id']}").json()["estado"] == "bloqueado"
    assert client.patch(f"/clientes/{c['id']}", json={"situacao": "ativo"}).status_code == 409
    neg = client.get("/relatorios/contas-saldo-negativo").json()
    assert neg[0]["conta_id"] == conta["id"] and neg[0]["dias_negativo"] == 30


def test_saldo_negativo_reiniciado_ao_regularizar(client, novo_cliente, nova_conta, relogio):
    c = novo_cliente()
    conta = nova_conta(c["id"], limite="1000.00")
    saque(client, conta["id"], "100.00")
    relogio.avancar(days=20)
    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": "100.00"})
    saque(client, conta["id"], "50.00")
    relogio.avancar(days=20)
    client.post("/rotinas/diaria")
    assert client.get(f"/clientes/{c['id']}").json()["situacao"] == "ativo"


# ---------------- regra 7 ----------------
def test_encerramento_conta(client, novo_cliente, nova_conta):
    conta, cartao, f = _cartao_com_fatura(client, novo_cliente, nova_conta)
    outro = client.post("/cartoes", json={"conta_id": conta["id"], "limite": "100.00"}).json()
    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": "10.00"})
    r = client.delete(f"/contas/{conta['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "saldo_nao_zerado"
    saque(client, conta["id"], "10.00")
    r = client.delete(f"/contas/{conta['id']}")
    assert r.status_code == 409 and r.json()["erro"] == "faturas_em_aberto"
    client.post(f"/faturas/{f['id']}/pagamento", json={"valor": "1000.00"})
    r = client.delete(f"/contas/{conta['id']}")
    assert r.status_code == 200 and r.json()["estado"] == "encerrada"
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "cancelado"
    assert client.get(f"/cartoes/{outro['id']}").json()["estado"] == "cancelado"
    assert client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": "1.00"}).status_code == 409


# ---------------- relatorios ----------------
def test_relatorio_maior_movimentacao(client, novo_cliente, nova_conta):
    a, b = novo_cliente(nome="Ana Souza"), novo_cliente(nome="Bruno Lima")
    ca = nova_conta(a["id"], saldo="1000.00")
    cb = nova_conta(b["id"], saldo="100.00")
    transf(client, ca["id"], cb["id"], "500.00")
    t = saque(client, cb["id"], "50.00").json()["transacao"]
    client.post(f"/transacoes/{t['id']}/estorno")
    r = client.get("/relatorios/clientes-maior-movimentacao",
                   params={"data_inicio": "2026-11-01", "data_fim": "2026-11-30"}).json()
    assert [(x["nome"], x["total_movimentado"]) for x in r] == [("Ana Souza", 1500.0), ("Bruno Lima", 600.0)]
    assert client.get("/relatorios/clientes-maior-movimentacao",
                      params={"data_inicio": "2026-12-01", "data_fim": "2026-11-01"}).status_code == 422
