from datetime import datetime, timedelta

from app import clock
from tests.conftest import AGORA, gerar_cpf


def saldo(client, conta_id):
    return client.get(f"/contas/{conta_id}").json()["saldo"]


# ------------------------------------------------------------ clientes / CRUD
class TestClientes:
    def test_crud(self, client):
        cpf = gerar_cpf()
        r = client.post("/clientes", json={"nome": "Ana Souza", "cpf": f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}",
                                           "email": "ANA@exemplo.com", "categoria": "premium"})
        assert r.status_code == 201
        c = r.json()
        assert c["cpf"] == cpf and c["email"] == "ana@exemplo.com" and c["situacao"] == "ativo"
        assert client.get(f"/clientes/{c['id']}").status_code == 200
        r = client.patch(f"/clientes/{c['id']}", json={"categoria": "empresarial"})
        assert r.json()["categoria"] == "empresarial"
        assert client.delete(f"/clientes/{c['id']}").status_code == 204
        assert client.get(f"/clientes/{c['id']}").status_code == 404

    def test_validacoes(self, client, novo_cliente):
        base = {"nome": "Joao", "cpf": "123.456.789-00", "email": "a@b.com", "categoria": "comum"}
        assert client.post("/clientes", json=base).status_code == 422  # CPF invalido
        base["cpf"] = gerar_cpf()
        assert client.post("/clientes", json={**base, "email": "invalido"}).status_code == 422
        assert client.post("/clientes", json={**base, "categoria": "vip"}).status_code == 422
        assert client.post("/clientes", json=base).status_code == 201
        assert client.post("/clientes", json={**base, "email": "x@y.com"}).status_code == 409
        c = novo_cliente()
        assert client.patch(f"/clientes/{c['id']}", json={"cpf": gerar_cpf()}).status_code == 422

    def test_nao_exclui_cliente_com_conta(self, client, nova_conta):
        conta = nova_conta()
        assert client.delete(f"/clientes/{conta['cliente_id']}").status_code == 409


# ----------------------------------------------------------------- operacoes
class TestOperacoes:
    def test_deposito_saque(self, client, nova_conta):
        conta = nova_conta(saldo="500.00")
        r = client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": "200.00"})
        assert r.status_code == 201
        assert r.json()["estado"] == "efetivada"
        assert saldo(client, conta["id"]) == "300.00"
        assert client.post("/transacoes/depositos", json={"conta_id": conta["id"], "valor": "-5"}).status_code == 422
        assert client.post("/transacoes/depositos", json={"conta_id": conta["id"], "valor": "1.001"}).status_code == 422
        assert client.post("/transacoes/depositos", json={"conta_id": 999, "valor": "1"}).status_code == 404

    def test_limite_diario_saque_comum(self, client, nova_conta, novo_cliente):
        cli = novo_cliente("comum")
        c1 = nova_conta(cliente=cli, saldo="5000.00")
        c2 = nova_conta(cliente=cli, saldo="5000.00")
        assert client.post("/transacoes/saques", json={"conta_id": c1["id"], "valor": "600.00"}).status_code == 201
        # limite acumulado por cliente: 600 + 400 = 1000 (ok); +0.01 excede
        assert client.post("/transacoes/saques", json={"conta_id": c2["id"], "valor": "400.00"}).status_code == 201
        r = client.post("/transacoes/saques", json={"conta_id": c1["id"], "valor": "0.01"})
        assert r.status_code == 422 and "Limite diario" in r.json()["detail"]
        clock.fixar(AGORA + timedelta(days=1))
        assert client.post("/transacoes/saques", json={"conta_id": c1["id"], "valor": "1000.00"}).status_code == 201

    def test_limites_saque_por_categoria(self, client, nova_conta):
        for cat, limite in (("premium", "5000.00"), ("empresarial", "20000.00")):
            conta = nova_conta(cat, saldo="100000.00")
            assert client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": limite}).status_code == 201
            assert client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": "0.01"}).status_code == 422

    def test_limite_por_transferencia(self, client, nova_conta):
        for cat, limite in (("comum", "5000.00"), ("premium", "50000.00"), ("empresarial", "200000.00")):
            origem = nova_conta(cat, saldo="500000.00")
            destino = nova_conta()
            excesso = str(float(limite) + 0.01)
            r = client.post("/transacoes/transferencias", json={
                "conta_origem_id": origem["id"], "conta_destino_id": destino["id"], "valor": f"{float(excesso):.2f}"})
            assert r.status_code == 422
            r = client.post("/transacoes/transferencias", json={
                "conta_origem_id": origem["id"], "conta_destino_id": destino["id"], "valor": limite})
            assert r.status_code == 201

    def test_limite_de_credito(self, client, nova_conta):
        conta = nova_conta(limite="300.00", saldo="100.00")
        r = client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": "400.00"})
        assert r.status_code == 201
        assert saldo(client, conta["id"]) == "-300.00"
        r = client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": "0.01"})
        assert r.status_code == 422 and "Saldo insuficiente" in r.json()["detail"]
        assert client.get(f"/contas/{conta['id']}").json()["negativo_desde"] is not None

    def test_conta_bloqueada_ou_cliente_bloqueado(self, client, nova_conta):
        conta = nova_conta(saldo="100.00")
        client.patch(f"/contas/{conta['id']}", json={"estado": "bloqueada"})
        assert client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": "1"}).status_code == 409
        # deposito em conta bloqueada e permitido
        assert client.post("/transacoes/depositos", json={"conta_id": conta["id"], "valor": "1"}).status_code == 201
        client.patch(f"/contas/{conta['id']}", json={"estado": "ativa"})
        client.patch(f"/clientes/{conta['cliente_id']}", json={"situacao": "bloqueado"})
        r = client.post("/transacoes/transferencias", json={
            "conta_origem_id": conta["id"], "conta_destino_id": nova_conta()["id"], "valor": "1"})
        assert r.status_code == 409

    def test_transferencia_mesma_conta(self, client, nova_conta):
        c = nova_conta(saldo="10")
        r = client.post("/transacoes/transferencias", json={
            "conta_origem_id": c["id"], "conta_destino_id": c["id"], "valor": "1"})
        assert r.status_code == 422


# ------------------------------------------------------------------- tarifas
class TestTarifas:
    def test_franquia_comum(self, client, nova_conta):
        conta = nova_conta("comum", saldo="1000.00")
        tarifas = []
        for _ in range(4):
            r = client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": "10.00"})
            tarifas.append(r.json()["tarifa"])
        assert [t["estado"] for t in tarifas] == ["isenta", "isenta", "isenta", "cobrada"]
        assert tarifas[3]["valor"] == "2.50"
        assert saldo(client, conta["id"]) == "957.50"
        assert len(client.get(f"/contas/{conta['id']}/tarifas?estado=cobrada").json()) == 1

    def test_transferencia_mesmo_cliente_isenta(self, client, nova_conta, novo_cliente):
        cli = novo_cliente("comum")
        a, b = nova_conta(cliente=cli, saldo="1000"), nova_conta(cliente=cli)
        for _ in range(5):
            r = client.post("/transacoes/transferencias", json={
                "conta_origem_id": a["id"], "conta_destino_id": b["id"], "valor": "10"})
            assert r.json()["tarifa"] is None
        assert saldo(client, a["id"]) == "950.00"
        # transferencia a terceiro consome franquia (ainda integral)
        r = client.post("/transacoes/transferencias", json={
            "conta_origem_id": a["id"], "conta_destino_id": nova_conta()["id"], "valor": "10"})
        assert r.json()["tarifa"]["estado"] == "isenta"

    def test_premium_ilimitado(self, client, nova_conta):
        conta = nova_conta("premium", saldo="1000")
        for _ in range(10):
            r = client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": "1"})
            assert r.json()["tarifa"]["estado"] == "isenta"
        assert saldo(client, conta["id"]) == "990.00"

    def test_tarifa_mensal_e_receita(self, client, nova_conta):
        comum = nova_conta("comum", saldo="100")
        premium = nova_conta("premium", saldo="100")
        emp = nova_conta("empresarial", saldo="1000")
        r = client.post("/rotinas/tarifas-mensais?competencia=2026-11")
        assert r.status_code == 200 and r.json()["detalhes"]["geradas"] == 3
        assert saldo(client, comum["id"]) == "70.00"
        assert saldo(client, premium["id"]) == "100.00"
        assert saldo(client, emp["id"]) == "880.00"
        # idempotente
        assert client.post("/rotinas/tarifas-mensais?competencia=2026-11").json()["detalhes"]["geradas"] == 0
        rec = client.get("/relatorios/receita-tarifas").json()
        por = {p["categoria"]: p["total"] for p in rec["por_categoria"]}
        assert por == {"comum": "30.00", "premium": "0.00", "empresarial": "120.00"}
        assert rec["total_geral"] == "150.00"


# ------------------------------------------------------------------- estorno
class TestEstorno:
    def test_estorno_transferencia(self, client, nova_conta):
        a, b = nova_conta(saldo="1000"), nova_conta()
        t = client.post("/transacoes/transferencias", json={
            "conta_origem_id": a["id"], "conta_destino_id": b["id"], "valor": "300"}).json()
        clock.fixar(AGORA + timedelta(hours=23, minutes=59))
        r = client.post(f"/transacoes/{t['id']}/estorno")
        assert r.status_code == 201
        e = r.json()
        assert e["tipo"] == "estorno" and e["transacao_original_id"] == t["id"]
        assert saldo(client, a["id"]) == "1000.00" and saldo(client, b["id"]) == "0.00"
        assert client.get(f"/transacoes/{t['id']}").json()["estado"] == "estornada"
        assert client.post(f"/transacoes/{t['id']}/estorno").status_code == 409
        assert client.post(f"/transacoes/{e['id']}/estorno").status_code == 422
        extrato = client.get(f"/contas/{a['id']}/extrato").json()
        assert [l["efeito"] for l in extrato["lancamentos"]] == ["1000.00", "-300.00", "300.00"]

    def test_estorno_fora_do_prazo(self, client, nova_conta):
        a = nova_conta(saldo="100")
        t = client.post("/transacoes/saques", json={"conta_id": a["id"], "valor": "50"}).json()
        clock.fixar(AGORA + timedelta(hours=24, seconds=1))
        assert client.post(f"/transacoes/{t['id']}/estorno").status_code == 422

    def test_estorno_libera_limite_diario(self, client, nova_conta):
        a = nova_conta(saldo="5000")
        t = client.post("/transacoes/saques", json={"conta_id": a["id"], "valor": "1000"}).json()
        client.post(f"/transacoes/{t['id']}/estorno")
        assert client.post("/transacoes/saques", json={"conta_id": a["id"], "valor": "1000"}).status_code == 201


# ------------------------------------------------------------ cartoes/faturas
class TestCartoesFaturas:
    def _cartao(self, client, conta, limite="2000"):
        r = client.post("/cartoes", json={"conta_id": conta["id"], "limite": limite})
        assert r.status_code == 201
        return r.json()

    def test_crud_cartao(self, client, nova_conta):
        cartao = self._cartao(client, nova_conta())
        assert len(cartao["numero"]) == 16
        assert client.patch(f"/cartoes/{cartao['id']}", json={"estado": "bloqueado"}).json()["motivo_bloqueio"] == "manual"
        assert client.patch(f"/cartoes/{cartao['id']}", json={"estado": "ativo"}).json()["estado"] == "ativo"
        assert client.delete(f"/cartoes/{cartao['id']}").json()["estado"] == "cancelado"
        assert client.patch(f"/cartoes/{cartao['id']}", json={"limite": "10"}).status_code == 409

    def test_fatura_atrasada_juros_e_bloqueio(self, client, nova_conta):
        cartao = self._cartao(client, nova_conta("comum"))
        f = client.post(f"/cartoes/{cartao['id']}/faturas",
                        json={"mes_referencia": "2026-10", "valor": "1000.00"}).json()
        assert f["data_vencimento"] == "2026-11-10"
        assert f["estado"] == "atrasada"  # hoje = 17/11, 7 dias de atraso
        assert f["juros"] == "18.67"     # 1000 * 8% * 7/30
        assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "ativo"

        clock.fixar(datetime(2026, 11, 21, 9))  # 11 dias de atraso
        r = client.post("/rotinas/processamento-diario").json()
        assert r["detalhes"]["cartoes_bloqueados_atraso"] == 1
        c = client.get(f"/cartoes/{cartao['id']}").json()
        assert c["estado"] == "bloqueado" and c["motivo_bloqueio"] == "atraso_fatura"
        assert client.patch(f"/cartoes/{cartao['id']}", json={"estado": "ativo"}).status_code == 409

        f = client.get(f"/cartoes/{cartao['id']}/faturas").json()[0]
        assert f["juros"] == "29.33" and f["valor_total"] == "1029.33"
        assert client.post(f"/faturas/{f['id']}/pagamento", json={"valor": "1000.00"}).status_code == 422
        r = client.post(f"/faturas/{f['id']}/pagamento", json={"valor": "1029.33"})
        assert r.status_code == 200 and r.json()["estado"] == "paga"
        assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "ativo"
        assert client.post(f"/faturas/{f['id']}/pagamento", json={"valor": "1029.33"}).status_code == 409

    def test_juros_por_categoria(self, client, nova_conta):
        for cat, juros in (("premium", "11.67"), ("empresarial", "7.00")):
            cartao = self._cartao(client, nova_conta(cat))
            f = client.post(f"/cartoes/{cartao['id']}/faturas",
                            json={"mes_referencia": "2026-10", "valor": "1000.00"}).json()
            assert f["juros"] == juros

    def test_fatura_ciclo(self, client, nova_conta):
        cartao = self._cartao(client, nova_conta())
        f = client.post(f"/cartoes/{cartao['id']}/faturas",
                        json={"mes_referencia": "2026-11", "valor": "100"}).json()
        assert f["estado"] == "aberta"
        assert client.post(f"/cartoes/{cartao['id']}/faturas",
                           json={"mes_referencia": "2026-11", "valor": "100"}).status_code == 409
        assert client.post(f"/cartoes/{cartao['id']}/faturas",
                           json={"mes_referencia": "2026-12", "valor": "5000"}).status_code == 422
        clock.fixar(datetime(2026, 12, 2))
        assert client.get(f"/faturas/{f['id']}").json()["estado"] == "fechada"


# -------------------------------------------------------------- encerramento
class TestEncerramento:
    def test_regras_encerramento(self, client, nova_conta):
        conta = nova_conta(saldo="10")
        cartao = client.post("/cartoes", json={"conta_id": conta["id"], "limite": "500"}).json()
        assert client.delete(f"/contas/{conta['id']}").status_code == 409  # saldo != 0
        client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": "10"})
        f = client.post(f"/cartoes/{cartao['id']}/faturas",
                        json={"mes_referencia": "2026-11", "valor": "50"}).json()
        r = client.delete(f"/contas/{conta['id']}")
        assert r.status_code == 409 and "fatura" in r.json()["detail"]
        client.post(f"/faturas/{f['id']}/pagamento", json={"valor": "50.00"})
        r = client.delete(f"/contas/{conta['id']}")
        assert r.status_code == 200 and r.json()["estado"] == "encerrada"
        assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "cancelado"
        assert client.post("/transacoes/depositos", json={"conta_id": conta["id"], "valor": "1"}).status_code == 409
        assert client.delete(f"/contas/{conta['id']}").status_code == 409


# ------------------------------------------------------ saldo negativo > 30d
class TestSaldoNegativo:
    def test_bloqueio_cliente_e_cartoes(self, client, nova_conta, novo_cliente):
        cli = novo_cliente()
        conta = nova_conta(cliente=cli, limite="500")
        outra = nova_conta(cliente=cli, saldo="100")
        cartao = client.post("/cartoes", json={"conta_id": outra["id"], "limite": "100"}).json()
        client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": "100"})

        clock.fixar(AGORA + timedelta(days=30))
        assert client.post("/rotinas/processamento-diario").json()["detalhes"]["clientes_bloqueados_saldo_negativo"] == 0
        clock.fixar(AGORA + timedelta(days=30, minutes=1))
        r = client.post("/rotinas/processamento-diario").json()["detalhes"]
        assert r["clientes_bloqueados_saldo_negativo"] == 1 and r["cartoes_bloqueados_saldo_negativo"] == 1
        assert client.get(f"/clientes/{cli['id']}").json()["situacao"] == "bloqueado"
        assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "bloqueado"

        # nao desbloqueia enquanto negativo; regulariza e desbloqueia (cartoes voltam)
        assert client.patch(f"/clientes/{cli['id']}", json={"situacao": "ativo"}).status_code == 409
        client.post("/transacoes/depositos", json={"conta_id": conta["id"], "valor": "100"})
        assert client.patch(f"/clientes/{cli['id']}", json={"situacao": "ativo"}).status_code == 200
        assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "ativo"

    def test_bloqueio_tardio_na_operacao(self, client, nova_conta):
        conta = nova_conta(limite="500")
        client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": "100"})
        clock.fixar(AGORA + timedelta(days=31))
        assert client.post("/transacoes/saques", json={"conta_id": conta["id"], "valor": "1"}).status_code == 409
        assert client.get(f"/clientes/{conta['cliente_id']}").json()["situacao"] == "bloqueado"


# ---------------------------------------------------------------- relatorios
class TestRelatorios:
    def test_movimentacao_e_negativas(self, client, nova_conta, novo_cliente):
        a = nova_conta(cliente=novo_cliente(nome="Maior"), saldo="3000")
        b = nova_conta(cliente=novo_cliente(nome="Menor"), saldo="100", limite="200")
        client.post("/transacoes/transferencias", json={
            "conta_origem_id": a["id"], "conta_destino_id": b["id"], "valor": "500"})
        client.post("/transacoes/saques", json={"conta_id": b["id"], "valor": "750"})
        rank = client.get("/relatorios/clientes-maior-movimentacao",
                          params={"inicio": "2026-11-01", "fim": "2026-11-30"}).json()
        assert [(r["nome"], r["valor_movimentado"]) for r in rank] == [("Maior", "3500.00"), ("Menor", "1350.00")]
        assert client.get("/relatorios/clientes-maior-movimentacao",
                          params={"inicio": "2026-12-01", "fim": "2026-11-01"}).status_code == 422

        neg = client.get("/relatorios/contas-saldo-negativo").json()
        assert len(neg) == 1 and neg[0]["conta_id"] == b["id"] and neg[0]["saldo"] == "-150.00"


def test_poupanca_sem_limite(client, novo_cliente):
    c = novo_cliente()
    r = client.post("/contas", json={"cliente_id": c["id"], "tipo": "poupanca", "limite_credito": "100"})
    assert r.status_code == 422
