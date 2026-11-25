from datetime import timedelta
from decimal import Decimal
from fastapi import status
from app.models.cartao import Cartao
from app.config import SituacaoCliente, EstadoCartao, get_current_time


def test_relatorio_clientes_maior_movimentacao(client, conta_comum, conta_premium):
    # Movimenta conta comum
    client.post("/transacoes/deposito", json={"conta_id": conta_comum.id, "valor": "500.00"})
    client.post("/transacoes/saque", json={"conta_id": conta_comum.id, "valor": "200.00"})

    # Movimenta conta premium com valor maior
    client.post("/transacoes/deposito", json={"conta_id": conta_premium.id, "valor": "4000.00"})

    response = client.get("/relatorios/clientes-maior-movimentacao")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    clientes = data["clientes"]
    assert len(clientes) >= 2

    # Cliente premium deve estar no topo (4000 > 700)
    assert clientes[0]["cliente_id"] == conta_premium.cliente_id
    assert Decimal(clientes[0]["total_movimentado"]) == Decimal("4000.00")
    assert clientes[1]["cliente_id"] == conta_comum.cliente_id
    assert Decimal(clientes[1]["total_movimentado"]) == Decimal("700.00")


def test_relatorio_contas_saldo_negativo(client, db, conta_comum, conta_premium):
    # Define saldo negativo para conta_comum
    conta_comum.saldo = Decimal("-250.00")
    conta_comum.data_saldo_negativo_desde = get_current_time() - timedelta(days=5)
    db.commit()

    response = client.get("/relatorios/contas-saldo-negativo")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total_contas_negativas"] == 1
    assert data["contas"][0]["conta_id"] == conta_comum.id
    assert Decimal(data["contas"][0]["saldo"]) == Decimal("-250.00")
    assert data["contas"][0]["dias_negativo"] >= 5


def test_relatorio_receita_tarifas_categoria(client, db, conta_comum, conta_premium):
    # Lança tarifa cobrada para conta_comum (categoria comum)
    client.post("/tarifas", json={
        "conta_id": conta_comum.id,
        "tipo": "manutencao_mensal",
        "valor": "30.00",
        "estado": "cobrada"
    })

    response = client.get("/relatorios/receita-tarifas-categoria")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert Decimal(data["total_geral"]) >= Decimal("30.00")

    detalhe_comum = next(item for item in data["detalhamento"] if item["categoria"] == "comum")
    assert Decimal(detalhe_comum["total_arrecadado"]) >= Decimal("30.00")
    assert detalhe_comum["quantidade_tarifas"] >= 1


def test_regra_6_bloqueio_saldo_negativo_mais_de_30_dias(client, db, conta_comum):
    # Cria cartão ativo para a conta
    cartao = Cartao(
        conta_id=conta_comum.id,
        numero="4999999999999999",
        limite=Decimal("2000.00"),
        estado=EstadoCartao.ATIVO,
    )
    db.add(cartao)

    # Define saldo negativo há 35 dias (> 30 dias)
    conta_comum.saldo = Decimal("-100.00")
    conta_comum.data_saldo_negativo_desde = get_current_time() - timedelta(days=35)
    db.commit()

    # Executa rotina de verificação de inadimplência
    response = client.post("/relatorios/processar-saldo-negativo-prolongado")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["clientes_bloqueados"] >= 1
    assert data["cartoes_bloqueados"] >= 1

    # Confirma que cliente e cartão foram bloqueados
    db.refresh(conta_comum.cliente)
    db.refresh(cartao)

    assert conta_comum.cliente.situacao == SituacaoCliente.BLOQUEADO
    assert cartao.estado == EstadoCartao.BLOQUEADO
