from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.conta import Conta
from app.models.cliente import Cliente
from app.models.transacao import Transacao
from app.models.tarifa import Tarifa
from app.schemas.relatorio import (
    ClienteMovimentacaoItem,
    ContaSaldoNegativoItem,
    ReceitaTarifasCategoriaItem,
)
from app.config import EstadoTransacao, EstadoTarifa, CategoriaCliente
from app.utils import utc_now


def relatorio_clientes_maior_movimentacao(
    db: Session,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    limite: int = 10,
) -> List[ClienteMovimentacaoItem]:
    """
    Relatório: clientes com maior movimentação no período.
    Soma o valor das transações efetivadas (depósito, saque, transferência de origem) de cada cliente.
    """
    query = (
        db.query(
            Cliente.id.label("cliente_id"),
            Cliente.nome.label("nome"),
            Cliente.cpf.label("cpf"),
            Cliente.categoria.label("categoria"),
            func.coalesce(func.sum(Transacao.valor), Decimal("0.00")).label("total_movimentado"),
            func.count(Transacao.id).label("total_transacoes"),
        )
        .join(Conta, Conta.cliente_id == Cliente.id)
        .join(Transacao, Transacao.conta_id == Conta.id)
        .filter(Transacao.estado == EstadoTransacao.EFETIVADA)
    )

    if data_inicio:
        query = query.filter(Transacao.data >= data_inicio)
    if data_fim:
        query = query.filter(Transacao.data <= data_fim)

    resultados = (
        query.group_by(Cliente.id, Cliente.nome, Cliente.cpf, Cliente.categoria)
        .order_by(func.sum(Transacao.valor).desc())
        .limit(limite)
        .all()
    )

    return [
        ClienteMovimentacaoItem(
            cliente_id=r.cliente_id,
            nome=r.nome,
            cpf=r.cpf,
            categoria=r.categoria,
            total_movimentado=Decimal(str(r.total_movimentado)),
            total_transacoes=r.total_transacoes,
        )
        for r in resultados
    ]


def relatorio_contas_saldo_negativo(db: Session) -> List[ContaSaldoNegativoItem]:
    """
    Relatório: contas com saldo negativo.
    """
    contas = (
        db.query(Conta)
        .filter(Conta.saldo < Decimal("0.00"))
        .order_by(Conta.saldo.asc())
        .all()
    )

    agora = utc_now()
    itens = []
    for c in contas:
        dias_negativo = 0
        if c.data_saldo_negativo_inicio:
            dias_negativo = max(0, (agora - c.data_saldo_negativo_inicio).days)

        itens.append(
            ContaSaldoNegativoItem(
                conta_id=c.id,
                numero=c.numero,
                cliente_id=c.cliente.id,
                cliente_nome=c.cliente.nome,
                cliente_cpf=c.cliente.cpf,
                categoria=c.cliente.categoria,
                saldo=c.saldo,
                limite_credito=c.limite_credito,
                dias_negativo=dias_negativo,
                data_saldo_negativo_inicio=c.data_saldo_negativo_inicio,
            )
        )
    return itens


def relatorio_receita_tarifas_categoria(db: Session) -> List[ReceitaTarifasCategoriaItem]:
    """
    Relatório: receita de tarifas por categoria de cliente.
    """
    # Consulta das tarifas cobradas por categoria
    resultados = (
        db.query(
            Cliente.categoria.label("categoria"),
            func.coalesce(func.sum(Tarifa.valor), Decimal("0.00")).label("total_receita"),
            func.count(Tarifa.id).label("quantidade_tarifas"),
        )
        .join(Conta, Conta.cliente_id == Cliente.id)
        .join(Tarifa, Tarifa.conta_id == Conta.id)
        .filter(Tarifa.estado == EstadoTarifa.COBRADA)
        .group_by(Cliente.categoria)
        .all()
    )

    mapa_resultados = {
        r.categoria: (Decimal(str(r.total_receita)), r.quantidade_tarifas)
        for r in resultados
    }

    # Assegurar que todas as categorias apareçam no relatório
    itens = []
    for cat in CategoriaCliente:
        receita, qtd = mapa_resultados.get(cat, (Decimal("0.00"), 0))
        itens.append(
            ReceitaTarifasCategoriaItem(
                categoria=cat,
                total_receita=receita,
                quantidade_tarifas=qtd,
            )
        )
    return itens
