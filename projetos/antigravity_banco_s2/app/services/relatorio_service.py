from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models.conta import Conta
from app.models.cliente import Cliente
from app.models.transacao import Transacao
from app.models.tarifa import Tarifa
from app.models.cartao import Cartao
from app.schemas.relatorio import (
    ClienteMovimentacaoItem,
    RelatorioMovimentacaoResponse,
    ContaSaldoNegativoItem,
    RelatorioSaldoNegativoResponse,
    ReceitaTarifasCategoriaItem,
    RelatorioReceitaTarifasResponse,
    ProcessarInadimplenciaResponse,
)
from app.config import (
    CategoriaCliente,
    SituacaoCliente,
    EstadoTransacao,
    EstadoTarifa,
    EstadoCartao,
    DIAS_BLOQUEIO_SALDO_NEGATIVO,
    get_current_time,
)


def obter_clientes_maior_movimentacao(
    db: Session,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    limit: int = 10,
) -> RelatorioMovimentacaoResponse:
    """
    Relatório: clientes com maior movimentação no período (soma dos valores das transações efetivadas).
    """
    query = (
        db.query(
            Cliente.id.label("cliente_id"),
            Cliente.nome.label("nome"),
            Cliente.cpf.label("cpf"),
            Cliente.categoria.label("categoria"),
            func.coalesce(func.sum(Transacao.valor), Decimal("0.00")).label("total_movimentado"),
            func.count(Transacao.id).label("quantidade_transacoes"),
        )
        .join(Conta, Conta.cliente_id == Cliente.id)
        .join(Transacao, Transacao.conta_id == Conta.id)
        .filter(Transacao.estado == EstadoTransacao.EFETIVADA)
    )

    if data_inicio:
        query = query.filter(Transacao.data >= data_inicio)
    if data_fim:
        query = query.filter(Transacao.data <= data_fim)

    query = query.group_by(Cliente.id, Cliente.nome, Cliente.cpf, Cliente.categoria)
    query = query.order_by(desc("total_movimentado")).limit(limit)

    resultados = query.all()

    itens = [
        ClienteMovimentacaoItem(
            cliente_id=r.cliente_id,
            nome=r.nome,
            cpf=r.cpf,
            categoria=r.categoria,
            total_movimentado=Decimal(str(r.total_movimentado)),
            quantidade_transacoes=r.quantidade_transacoes,
        )
        for r in resultados
    ]

    return RelatorioMovimentacaoResponse(
        data_inicio=data_inicio,
        data_fim=data_fim,
        clientes=itens,
    )


def obter_contas_saldo_negativo(
    db: Session,
    data_ref: Optional[datetime] = None,
) -> RelatorioSaldoNegativoResponse:
    """
    Relatório: contas com saldo negativo.
    """
    if data_ref is None:
        data_ref = get_current_time()

    contas = db.query(Conta).filter(Conta.saldo < Decimal("0.00")).all()

    itens: List[ContaSaldoNegativoItem] = []
    for c in contas:
        dias = 0
        if c.data_saldo_negativo_desde:
            dias = max(0, (data_ref - c.data_saldo_negativo_desde).days)

        itens.append(
            ContaSaldoNegativoItem(
                conta_id=c.id,
                numero_conta=c.numero,
                cliente_id=c.cliente_id,
                nome_cliente=c.cliente.nome,
                cpf_cliente=c.cliente.cpf,
                categoria_cliente=c.cliente.categoria,
                saldo=c.saldo,
                limite_credito=c.limite_credito,
                data_saldo_negativo_desde=c.data_saldo_negativo_desde,
                dias_negativo=dias,
            )
        )

    itens.sort(key=lambda x: x.saldo)

    return RelatorioSaldoNegativoResponse(
        total_contas_negativas=len(itens),
        contas=itens,
    )


def obter_receita_tarifas_por_categoria(db: Session) -> RelatorioReceitaTarifasResponse:
    """
    Relatório: receita de tarifas por categoria de cliente.
    """
    # Inicializa todas as categorias com zero
    totais = {cat: {"total": Decimal("0.00"), "qtd": 0} for cat in CategoriaCliente}

    tarifas_cobradas = (
        db.query(
            Cliente.categoria,
            func.coalesce(func.sum(Tarifa.valor), Decimal("0.00")).label("total"),
            func.count(Tarifa.id).label("qtd"),
        )
        .join(Conta, Tarifa.conta_id == Conta.id)
        .join(Cliente, Conta.cliente_id == Cliente.id)
        .filter(Tarifa.estado == EstadoTarifa.COBRADA)
        .group_by(Cliente.categoria)
        .all()
    )

    total_geral = Decimal("0.00")
    for r in tarifas_cobradas:
        totais[r.categoria]["total"] = Decimal(str(r.total))
        totais[r.categoria]["qtd"] = r.qtd
        total_geral += Decimal(str(r.total))

    detalhamento = [
        ReceitaTarifasCategoriaItem(
            categoria=cat,
            total_arrecadado=totais[cat]["total"],
            quantidade_tarifas=totais[cat]["qtd"],
        )
        for cat in CategoriaCliente
    ]

    return RelatorioReceitaTarifasResponse(
        total_geral=total_geral,
        detalhamento=detalhamento,
    )


def processar_saldo_negativo_prolongado(
    db: Session,
    data_ref: Optional[datetime] = None,
) -> ProcessarInadimplenciaResponse:
    """
    Regra 6: Conta com saldo negativo por mais de 30 dias bloqueia o cliente e todos os seus cartoes.
    """
    if data_ref is None:
        data_ref = get_current_time()

    contas_negativas = (
        db.query(Conta)
        .filter(
            Conta.saldo < Decimal("0.00"),
            Conta.data_saldo_negativo_desde.isnot(None),
        )
        .all()
    )

    clientes_bloqueados_count = 0
    cartoes_bloqueados_count = 0
    clientes_afetados = set()

    for conta in contas_negativas:
        dias_negativo = (data_ref - conta.data_saldo_negativo_desde).days
        if dias_negativo > DIAS_BLOQUEIO_SALDO_NEGATIVO:
            cliente = conta.cliente
            if cliente.id not in clientes_afetados:
                if cliente.situacao != SituacaoCliente.BLOQUEADO:
                    cliente.situacao = SituacaoCliente.BLOQUEADO
                    clientes_bloqueados_count += 1
                clientes_afetados.add(cliente.id)

                # Bloqueia todos os cartões de todas as contas do cliente
                for c in cliente.contas:
                    for cartao in c.cartoes:
                        if cartao.estado == EstadoCartao.ATIVO:
                            cartao.estado = EstadoCartao.BLOQUEADO
                            cartoes_bloqueados_count += 1

    db.commit()

    return ProcessarInadimplenciaResponse(
        clientes_bloqueados=clientes_bloqueados_count,
        cartoes_bloqueados=cartoes_bloqueados_count,
        mensagem=(
            f"Processamento concluído: {clientes_bloqueados_count} cliente(s) bloqueado(s) "
            f"e {cartoes_bloqueados_count} cartão(ões) bloqueado(s) por saldo negativo > {DIAS_BLOQUEIO_SALDO_NEGATIVO} dias."
        ),
    )
