from datetime import timedelta
from decimal import Decimal
from fastapi import status
from app.models.conta import Conta
from app.models.tarifa import Tarifa
from app.config import (
    TipoConta,
    EstadoConta,
    SituacaoCliente,
    TipoTransacao,
    EstadoTransacao,
    EstadoTarifa,
    get_current_time,
)


def test_deposito_sucesso(client, conta_comum):
    payload = {
        "conta_id": conta_comum.id,
        "valor": "500.00",
        "descricao": "Depósito teste"
    }
    response = client.post("/transacoes/deposito", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert Decimal(data["valor"]) == Decimal("500.00")
    assert data["tipo"] == "deposito"
    assert data["estado"] == "efetivada"

    # Verifica saldo atualizado (2000 + 500 = 2500)
    resp_conta = client.get(f"/contas/{conta_comum.id}")
    assert Decimal(resp_conta.json()["saldo"]) == Decimal("2500.00")


def test_deposito_valor_invalido(client, conta_comum):
    payload = {
        "conta_id": conta_comum.id,
        "valor": "-10.00"
    }
    response = client.post("/transacoes/deposito", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_regra_1_saque_limite_diario_comum(client, conta_comum):
    # Cliente comum tem limite diário de saque de R$ 1.000,00
    # Primeiro saque: 600.00 -> OK
    payload1 = {
        "conta_id": conta_comum.id,
        "valor": "600.00"
    }
    r1 = client.post("/transacoes/saque", json=payload1)
    assert r1.status_code == status.HTTP_201_CREATED

    # Segundo saque: 500.00 -> Ultrapassa 1000.00 acumulado no dia (600+500 = 1100 > 1000)
    payload2 = {
        "conta_id": conta_comum.id,
        "valor": "500.00"
    }
    r2 = client.post("/transacoes/saque", json=payload2)
    assert r2.status_code == status.HTTP_400_BAD_REQUEST
    assert "Limite diário de saque excedido" in r2.json()["detail"]

    # Terceiro saque: 400.00 -> Exatamente atinge o limite diário de 1000.00 (600+400 = 1000)
    payload3 = {
        "conta_id": conta_comum.id,
        "valor": "400.00"
    }
    r3 = client.post("/transacoes/saque", json=payload3)
    assert r3.status_code == status.HTTP_201_CREATED


def test_regra_1_saque_conta_bloqueada_falha(client, db, conta_comum):
    conta_comum.estado = EstadoConta.BLOQUEADA
    db.commit()

    payload = {"conta_id": conta_comum.id, "valor": "50.00"}
    response = client.post("/transacoes/saque", json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "contas ativas" in response.json()["detail"].lower()


def test_regra_1_saque_cliente_bloqueado_falha(client, db, conta_comum):
    conta_comum.cliente.situacao = SituacaoCliente.BLOQUEADO
    db.commit()

    payload = {"conta_id": conta_comum.id, "valor": "50.00"}
    response = client.post("/transacoes/saque", json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "clientes ativos" in response.json()["detail"].lower()


def test_regra_2_saldo_negativo_ate_limite_credito(client, db, conta_comum):
    # conta_comum: saldo 2000.00, limite 500.00 -> Disponível = 2500.00
    # Porém, cliente comum tem limite diário de saque de 1000.00.
    # Vamos ajustar o saldo para 100.00 e limite de crédito para 500.00.
    conta_comum.saldo = Decimal("100.00")
    db.commit()

    # Saque de 500.00 (fica saldo -400.00, que é >= -500.00) -> Permitido!
    payload = {"conta_id": conta_comum.id, "valor": "500.00"}
    resp = client.post("/transacoes/saque", json=payload)
    assert resp.status_code == status.HTTP_201_CREATED

    db.refresh(conta_comum)
    assert conta_comum.saldo == Decimal("-400.00")
    assert conta_comum.data_saldo_negativo_desde is not None

    # Agora saldo é -400.00. Tentativa de saque de 150.00 (resultaria em -550.00 < -500.00) -> Negado!
    payload_falha = {"conta_id": conta_comum.id, "valor": "150.00"}
    resp_falha = client.post("/transacoes/saque", json=payload_falha)
    assert resp_falha.status_code == status.HTTP_400_BAD_REQUEST
    assert "Saldo insuficiente" in resp_falha.json()["detail"]


def test_regra_1_transferencia_limite_categoria(client, conta_comum, conta_premium):
    # Cliente comum tem limite por transferência de R$ 5.000,00
    payload = {
        "conta_id": conta_comum.id,
        "conta_destino_id": conta_premium.id,
        "valor": "5001.00",
    }
    response = client.post("/transacoes/transferencia", json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "limite por transferência" in response.json()["detail"]


def test_regra_3_transferencia_mesmo_cliente_isenta(client, db, cliente_comum, conta_comum):
    # Cria uma segunda conta para o mesmo cliente
    conta2 = Conta(
        cliente_id=cliente_comum.id,
        numero="0001-2",
        tipo=TipoConta.POUPANCA,
        saldo=Decimal("50.00"),
        limite_credito=Decimal("0.00"),
        estado=EstadoConta.ATIVA,
    )
    db.add(conta2)
    db.commit()
    db.refresh(conta2)

    payload = {
        "conta_id": conta_comum.id,
        "conta_destino_id": conta2.id,
        "valor": "300.00",
    }
    response = client.post("/transacoes/transferencia", json=payload)
    assert response.status_code == status.HTTP_201_CREATED

    # Confirma que nenhuma tarifa foi gerada
    tarifas = db.query(Tarifa).filter(Tarifa.conta_id == conta_comum.id).all()
    assert len(tarifas) == 0


def test_regra_3_transferencia_franquia_e_tarifa_excedente(client, db, conta_comum, conta_premium):
    # Cliente Comum tem franquia de 3 transações isentas por mês
    # Vamos aumentar o saldo de conta_comum para suportar várias transferências
    conta_comum.saldo = Decimal("5000.00")
    db.commit()

    # 3 transferências isentas (1ª, 2ª e 3ª)
    for i in range(3):
        payload = {
            "conta_id": conta_comum.id,
            "conta_destino_id": conta_premium.id,
            "valor": "100.00",
        }
        resp = client.post("/transacoes/transferencia", json=payload)
        assert resp.status_code == status.HTTP_201_CREATED

    tarifas_antes = db.query(Tarifa).filter(Tarifa.conta_id == conta_comum.id).all()
    assert len(tarifas_antes) == 0

    # 4ª transferência: esgotou a franquia de 3! Deve gerar tarifa (R$ 10,00)
    payload_4 = {
        "conta_id": conta_comum.id,
        "conta_destino_id": conta_premium.id,
        "valor": "100.00",
    }
    resp_4 = client.post("/transacoes/transferencia", json=payload_4)
    assert resp_4.status_code == status.HTTP_201_CREATED

    tarifas_depois = db.query(Tarifa).filter(Tarifa.conta_id == conta_comum.id).all()
    assert len(tarifas_depois) == 1
    assert tarifas_depois[0].tipo == "transferencia_excedente"
    assert tarifas_depois[0].valor == Decimal("10.00")
    assert tarifas_depois[0].estado == EstadoTarifa.COBRADA


def test_regra_4_estorno_sucesso_dentro_24h(client, db, conta_comum):
    # Realiza um depósito
    dep_payload = {"conta_id": conta_comum.id, "valor": "300.00"}
    dep_resp = client.post("/transacoes/deposito", json=dep_payload)
    transacao_id = dep_resp.json()["id"]

    saldo_apos_dep = Decimal(client.get(f"/contas/{conta_comum.id}").json()["saldo"])

    # Estorna a transação
    estorno_resp = client.post(f"/transacoes/{transacao_id}/estorno")
    assert estorno_resp.status_code == status.HTTP_201_CREATED
    estorno_data = estorno_resp.json()
    assert estorno_data["tipo"] == "estorno"
    assert estorno_data["transacao_origem_id"] == transacao_id

    # Saldo deve ter sido revertido
    saldo_apos_estorno = Decimal(client.get(f"/contas/{conta_comum.id}").json()["saldo"])
    assert saldo_apos_estorno == saldo_apos_dep - Decimal("300.00")


def test_regra_4_estorno_apos_24h_falha(client, db, conta_comum):
    # Simula depósito feito há 25 horas
    data_passada = get_current_time() - timedelta(hours=25)
    dep_payload = {
        "conta_id": conta_comum.id,
        "valor": "200.00",
        "data": data_passada.isoformat(),
    }
    dep_resp = client.post("/transacoes/deposito", json=dep_payload)
    transacao_id = dep_resp.json()["id"]

    # Tentativa de estorno deve falhar
    estorno_resp = client.post(f"/transacoes/{transacao_id}/estorno")
    assert estorno_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "prazo limite é de 24 horas" in estorno_resp.json()["detail"]


def test_extrato_da_conta(client, conta_comum):
    client.post("/transacoes/deposito", json={"conta_id": conta_comum.id, "valor": "100.00"})
    client.post("/transacoes/saque", json={"conta_id": conta_comum.id, "valor": "50.00"})

    resp = client.get(f"/contas/{conta_comum.id}/extrato")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["conta_id"] == conta_comum.id
    assert len(data["transacoes"]) == 2
