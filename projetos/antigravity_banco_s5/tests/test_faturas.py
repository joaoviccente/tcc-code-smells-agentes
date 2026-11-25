from datetime import date, timedelta
from decimal import Decimal
from fastapi import status


def test_criar_e_obter_fatura(client):
    cli = client.post("/clientes", json={
        "nome": "Cliente Fatura",
        "cpf": "52998224725",
        "email": "fat@exemplo.com",
    }).json()

    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "9001"}).json()
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "4111222233334444"}).json()

    # Vencimento futuro (em 15 dias)
    vencimento = (date.today() + timedelta(days=15)).isoformat()
    res = client.post("/faturas", json={
        "cartao_id": cartao["id"],
        "mes_referencia": "2026-11",
        "valor": 500.0,
        "data_vencimento": vencimento,
    })
    assert res.status_code == status.HTTP_201_CREATED
    fat = res.json()
    assert fat["estado"] == "aberta"
    assert Decimal(str(fat["juros_acumulados"])) == Decimal("0.00")
    assert Decimal(str(fat["valor_total_atual"])) == Decimal("500.00")


def test_regra_5_fatura_atrasada_juros_e_bloqueio_cartao_comum(client):
    # Regra 5: Fatura não paga até o vencimento passa ao estado atrasada e acumula juros conforme a categoria.
    # Categoria Comum: 8% ao mês (0.08)
    # Após 10 dias de atraso, o cartão é bloqueado.
    cli = client.post("/clientes", json={
        "nome": "Cliente Atrasado Comum",
        "cpf": "52998224725",
        "email": "atraso.comum@exemplo.com",
        "categoria": "comum",
    }).json()

    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "9002"}).json()
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "4111000011112222"}).json()

    # Fatura vencida há 15 dias (> 10 dias)
    vencimento_passado = (date.today() - timedelta(days=15)).isoformat()
    fat = client.post("/faturas", json={
        "cartao_id": cartao["id"],
        "mes_referencia": "2026-10",
        "valor": 1000.0,
        "data_vencimento": vencimento_passado,
    }).json()

    # Consultar fatura -> deve atualizar para atrasada e calcular juros
    res = client.get(f"/faturas/{fat['id']}")
    assert res.status_code == status.HTTP_200_OK
    fat_atual = res.json()
    assert fat_atual["estado"] == "atrasada"
    assert fat_atual["dias_atraso"] == 15

    # Cálculo esperado de juros: 1000 * (0.08 / 30) * 15 = 40.00
    esperado_juros = Decimal("40.00")
    assert Decimal(str(fat_atual["juros_acumulados"])) == esperado_juros
    assert Decimal(str(fat_atual["valor_total_atual"])) == Decimal("1040.00")

    # Verificar que o cartão foi bloqueado (atraso > 10 dias)
    cartao_atual = client.get(f"/cartoes/{cartao['id']}").json()
    assert cartao_atual["estado"] == "bloqueado"


def test_regra_5_juros_categoria_premium(client):
    # Categoria Premium: juros de atraso 5% ao mês (0.05)
    cli = client.post("/clientes", json={
        "nome": "Cliente Premium Atraso",
        "cpf": "52998224725",
        "email": "prem.atraso@exemplo.com",
        "categoria": "premium",
    }).json()

    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "9003"}).json()
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "4111333344445555"}).json()

    vencimento_passado = (date.today() - timedelta(days=6)).isoformat()
    fat = client.post("/faturas", json={
        "cartao_id": cartao["id"],
        "mes_referencia": "2026-10",
        "valor": 1000.0,
        "data_vencimento": vencimento_passado,
    }).json()

    fat_atual = client.get(f"/faturas/{fat['id']}").json()
    assert fat_atual["estado"] == "atrasada"
    # Cálculo esperado: 1000 * (0.05 / 30) * 6 = 10.00
    assert Decimal(str(fat_atual["juros_acumulados"])) == Decimal("10.00")

    # Com 6 dias de atraso (<= 10 dias), o cartão ainda NÃO deve estar bloqueado
    cartao_atual = client.get(f"/cartoes/{cartao['id']}").json()
    assert cartao_atual["estado"] == "ativo"


def test_regra_5_juros_categoria_empresarial(client):
    # Categoria Empresarial: juros de atraso 3% ao mês (0.03)
    cli = client.post("/clientes", json={
        "nome": "Empresa Atraso",
        "cpf": "99988877714",
        "email": "emp.atraso@exemplo.com",
        "categoria": "empresarial",
    }).json()

    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "9005"}).json()
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "4111888899990000"}).json()

    # Vencida há 10 dias: 1000 * (0.03 / 30) * 10 = 10.00
    vencimento_passado = (date.today() - timedelta(days=10)).isoformat()
    fat = client.post("/faturas", json={
        "cartao_id": cartao["id"],
        "mes_referencia": "2026-10",
        "valor": 1000.0,
        "data_vencimento": vencimento_passado,
    }).json()

    fat_atual = client.get(f"/faturas/{fat['id']}").json()
    assert fat_atual["estado"] == "atrasada"
    assert Decimal(str(fat_atual["juros_acumulados"])) == Decimal("10.00")



def test_pagar_fatura_debito_em_conta_e_desbloqueio(client):
    cli = client.post("/clientes", json={
        "nome": "Cliente Pagador",
        "cpf": "52998224725",
        "email": "pagador@exemplo.com",
        "categoria": "comum",
    }).json()

    conta = client.post("/contas", json={"cliente_id": cli["id"], "numero": "9004"}).json()
    cartao = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "4111666677778888"}).json()

    # Depositar na conta para ter saldo
    client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": 2000.0})

    # Fatura vencida há 12 dias -> bloqueia cartão
    vencimento_passado = (date.today() - timedelta(days=12)).isoformat()
    fat = client.post("/faturas", json={
        "cartao_id": cartao["id"],
        "mes_referencia": "2026-10",
        "valor": 500.0,
        "data_vencimento": vencimento_passado,
    }).json()

    # Dispara atualização e bloqueio do cartão
    client.get(f"/faturas/{fat['id']}")
    assert client.get(f"/cartoes/{cartao['id']}").json()["estado"] == "bloqueado"

    # Pagar fatura debitando da conta
    res_pag = client.post(f"/faturas/{fat['id']}/pagamento", json={
        "conta_origem_id": conta["id"],
    })
    assert res_pag.status_code == status.HTTP_200_OK
    fat_paga = res_pag.json()
    assert fat_paga["estado"] == "paga"

    # Saldo da conta foi debitado (500 + juros)
    conta_atual = client.get(f"/contas/{conta['id']}").json()
    assert Decimal(str(conta_atual["saldo"])) < Decimal("1500.00")

    # Cartão deve ter sido desbloqueado automaticamente
    cartao_atual = client.get(f"/cartoes/{cartao['id']}").json()
    assert cartao_atual["estado"] == "ativo"
