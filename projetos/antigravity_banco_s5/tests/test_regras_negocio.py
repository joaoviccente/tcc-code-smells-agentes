from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi import status
from tests.conftest import TestingSessionLocal
from app.models.conta import Conta


def test_regra_6_saldo_negativo_mais_de_30_dias_bloqueia_cliente_e_cartoes(client):
    # Regra 6: Conta com saldo negativo por mais de 30 dias bloqueia o cliente e todos os seus cartões.
    cli = client.post("/clientes", json={
        "nome": "Cliente Inadimplente 30 Dias",
        "cpf": "52998224725",
        "email": "inadimplente30@exemplo.com",
    }).json()

    conta = client.post("/contas", json={
        "cliente_id": cli["id"],
        "numero": "9901",
        "limite_credito": 500.0,
    }).json()

    cartao1 = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "4000999911112222"}).json()
    cartao2 = client.post("/cartoes", json={"conta_id": conta["id"], "numero": "4000999933334444"}).json()

    # Realizar saque para deixar saldo negativo (-100)
    client.post("/transacoes/saque", json={"conta_id": conta["id"], "valor": 100.0})

    # Simular data de saldo negativo há 35 dias no passado
    db = TestingSessionLocal()
    conta_db = db.query(Conta).filter(Conta.id == conta["id"]).first()
    conta_db.data_saldo_negativo_inicio = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=35)
    db.commit()
    db.close()

    # Executar rotina de verificação de inadimplência
    res_rotina = client.post("/rotinas/verificar-inadimplencia")
    assert res_rotina.status_code == status.HTTP_200_OK
    dados = res_rotina.json()
    assert dados["clientes_bloqueados_por_saldo_negativo"] >= 1

    # Verificar que cliente foi bloqueado
    cli_atual = client.get(f"/clientes/{cli['id']}").json()
    assert cli_atual["situacao"] == "bloqueado"

    # Verificar que todos os cartões foram bloqueados
    c1 = client.get(f"/cartoes/{cartao1['id']}").json()
    c2 = client.get(f"/cartoes/{cartao2['id']}").json()
    assert c1["estado"] == "bloqueado"
    assert c2["estado"] == "bloqueado"


def test_tarifas_mensais_por_categoria(client):
    # Regras por categoria:
    # Comum: tarifa mensal R$ 30,00
    # Premium: sem tarifa mensal (R$ 0,00, isenta)
    # Empresarial: tarifa mensal R$ 120,00

    # 1. Comum
    cli_comum = client.post("/clientes", json={
        "nome": "Cliente Comum Tarifa",
        "cpf": "52998224725",
        "email": "comum.tarifa@exemplo.com",
        "categoria": "comum",
    }).json()
    conta_comum = client.post("/contas", json={"cliente_id": cli_comum["id"], "numero": "1101", "limite_credito": 100.0}).json()
    res_comum = client.post(f"/contas/{conta_comum['id']}/cobrar-mensalidade")
    assert res_comum.status_code == status.HTTP_200_OK
    assert Decimal(str(res_comum.json()["valor"])) == Decimal("30.00")
    assert res_comum.json()["estado"] == "cobrada"
    c_comum_saldo = client.get(f"/contas/{conta_comum['id']}").json()["saldo"]
    assert Decimal(str(c_comum_saldo)) == Decimal("-30.00")

    # 2. Premium
    cli_prem = client.post("/clientes", json={
        "nome": "Cliente Premium Tarifa",
        "cpf": "11144477735",
        "email": "prem.tarifa@exemplo.com",
        "categoria": "premium",
    }).json()
    conta_prem = client.post("/contas", json={"cliente_id": cli_prem["id"], "numero": "1102"}).json()
    res_prem = client.post(f"/contas/{conta_prem['id']}/cobrar-mensalidade")
    assert res_prem.status_code == status.HTTP_200_OK
    assert Decimal(str(res_prem.json()["valor"])) == Decimal("0.00")
    assert res_prem.json()["estado"] == "isenta"

    # 3. Empresarial
    cli_emp = client.post("/clientes", json={
        "nome": "Empresa XPTO",
        "cpf": "99988877714",
        "email": "emp.tarifa@exemplo.com",
        "categoria": "empresarial",
    }).json()
    conta_emp = client.post("/contas", json={"cliente_id": cli_emp["id"], "numero": "1103", "limite_credito": 500.0}).json()
    res_emp = client.post(f"/contas/{conta_emp['id']}/cobrar-mensalidade")
    assert res_emp.status_code == status.HTTP_200_OK
    assert Decimal(str(res_emp.json()["valor"])) == Decimal("120.00")
    assert res_emp.json()["estado"] == "cobrada"
    c_emp_saldo = client.get(f"/contas/{conta_emp['id']}").json()["saldo"]
    assert Decimal(str(c_emp_saldo)) == Decimal("-120.00")
