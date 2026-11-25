from decimal import Decimal
from fastapi import status
from app.models.conta import Conta
from app.config import TipoConta, EstadoConta


def test_criar_tarifa_avulsa(client, conta_comum):
    payload = {
        "conta_id": conta_comum.id,
        "tipo": "segunda_via_cartao",
        "valor": "25.00",
        "estado": "cobrada"
    }
    saldo_anterior = conta_comum.saldo
    response = client.post("/tarifas", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert Decimal(data["valor"]) == Decimal("25.00")
    assert data["tipo"] == "segunda_via_cartao"

    # Confirma débito na conta
    resp_conta = client.get(f"/contas/{conta_comum.id}")
    assert Decimal(resp_conta.json()["saldo"]) == saldo_anterior - Decimal("25.00")


def test_processar_cobranca_mensal_categorias(client, db, cliente_comum, cliente_premium, cliente_empresarial):
    # Conta Comum: Tarifa mensal R$ 30,00
    conta_comum = Conta(
        cliente_id=cliente_comum.id,
        numero="1001-1",
        tipo=TipoConta.CORRENTE,
        saldo=Decimal("1000.00"),
        limite_credito=Decimal("200.00"),
        estado=EstadoConta.ATIVA,
    )
    # Conta Premium: Sem tarifa mensal (R$ 0,00)
    conta_premium = Conta(
        cliente_id=cliente_premium.id,
        numero="1002-2",
        tipo=TipoConta.CORRENTE,
        saldo=Decimal("5000.00"),
        limite_credito=Decimal("1000.00"),
        estado=EstadoConta.ATIVA,
    )
    # Conta Empresarial: Tarifa mensal R$ 120,00
    conta_empresarial = Conta(
        cliente_id=cliente_empresarial.id,
        numero="1003-3",
        tipo=TipoConta.CORRENTE,
        saldo=Decimal("20000.00"),
        limite_credito=Decimal("5000.00"),
        estado=EstadoConta.ATIVA,
    )
    db.add_all([conta_comum, conta_premium, conta_empresarial])
    db.commit()

    # Executa cobrança mensal
    response = client.post("/tarifas/cobranca-mensal")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # 2 contas cobradas: Comum (30) e Empresarial (120). Premium é isenta (0).
    assert data["contas_processadas"] == 2
    assert Decimal(data["total_cobrado"]) == Decimal("150.00")

    # Verifica saldos
    db.refresh(conta_comum)
    db.refresh(conta_premium)
    db.refresh(conta_empresarial)

    assert conta_comum.saldo == Decimal("970.00")      # 1000 - 30
    assert conta_premium.saldo == Decimal("5000.00")   # Sem tarifa
    assert conta_empresarial.saldo == Decimal("19880.00")  # 20000 - 120
