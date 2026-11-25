from datetime import datetime, date, time
from decimal import Decimal
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func

from app.models.transacao import Transacao
from app.models.conta import Conta
from app.models.cliente import Cliente
from app.models.tarifa import Tarifa
from app.schemas.transacao import (
    DepositoCreate,
    SaqueCreate,
    TransferenciaCreate,
    ExtratoResponse,
    TransacaoResponse,
)
from app.config import (
    TipoTransacao,
    EstadoTransacao,
    EstadoConta,
    SituacaoCliente,
    REGRAS_CATEGORIAS,
    LIMITE_HORAS_ESTORNO,
    VALOR_TARIFA_TRANSFERENCIA_PADRAO,
    EstadoTarifa,
    TipoTarifa,
    get_current_time,
)


def _atualizar_data_saldo_negativo(conta: Conta, data_ref: datetime) -> None:
    if conta.saldo < Decimal("0.00"):
        if conta.data_saldo_negativo_desde is None:
            conta.data_saldo_negativo_desde = data_ref
    else:
        conta.data_saldo_negativo_desde = None


def realizar_deposito(db: Session, deposito_in: DepositoCreate) -> Transacao:
    conta = db.query(Conta).filter(Conta.id == deposito_in.conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta com ID {deposito_in.conta_id} não encontrada."
        )

    if conta.estado != EstadoConta.ATIVA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Depósitos só são permitidos em contas ativas. Estado atual: '{conta.estado.value}'."
        )

    data_transacao = deposito_in.data or get_current_time()

    conta.saldo += deposito_in.valor
    _atualizar_data_saldo_negativo(conta, data_transacao)

    transacao = Transacao(
        conta_id=conta.id,
        tipo=TipoTransacao.DEPOSITO,
        valor=deposito_in.valor,
        data=data_transacao,
        estado=EstadoTransacao.EFETIVADA,
        descricao=deposito_in.descricao or "Depósito em conta corrente",
    )
    db.add(transacao)
    db.commit()
    db.refresh(transacao)
    return transacao


def realizar_saque(db: Session, saque_in: SaqueCreate) -> Transacao:
    """
    Regra 1: Saque so e permitido em conta ativa, de cliente ativo, respeitando o limite diario acumulado da categoria.
    Regra 2: O saldo pode ficar negativo ate o limite de credito da conta. Abaixo disso, a operacao e negada.
    """
    conta = db.query(Conta).filter(Conta.id == saque_in.conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta com ID {saque_in.conta_id} não encontrada."
        )

    # Verifica se a conta está ativa
    if conta.estado != EstadoConta.ATIVA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Saques só são permitidos em contas ativas. Estado atual: '{conta.estado.value}'."
        )

    # Verifica se o cliente está ativo
    cliente = conta.cliente
    if cliente.situacao != SituacaoCliente.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Saques só são permitidos para clientes ativos. Situação atual do cliente: '{cliente.situacao.value}'."
        )

    data_transacao = saque_in.data or get_current_time()
    regras = REGRAS_CATEGORIAS[cliente.categoria]

    # Verifica limite diário acumulado de saque para a data
    inicio_dia = datetime.combine(data_transacao.date(), time.min)
    fim_dia = datetime.combine(data_transacao.date(), time.max)

    saques_dia = (
        db.query(func.coalesce(func.sum(Transacao.valor), Decimal("0.00")))
        .filter(
            Transacao.conta_id == conta.id,
            Transacao.tipo == TipoTransacao.SAQUE,
            Transacao.estado == EstadoTransacao.EFETIVADA,
            Transacao.data >= inicio_dia,
            Transacao.data <= fim_dia,
        )
        .scalar()
    )

    if (saques_dia + saque_in.valor) > regras.limite_diario_saque:
        disponivel = max(Decimal("0.00"), regras.limite_diario_saque - saques_dia)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Limite diário de saque excedido para a categoria '{cliente.categoria.value}'. "
                f"Limite diário: R$ {regras.limite_diario_saque}, já sacado hoje: R$ {saques_dia}, "
                f"disponível para saque hoje: R$ {disponivel}."
            ),
        )

    # Regra 2: Saldo pode ficar negativo até o limite de crédito
    novo_saldo = conta.saldo - saque_in.valor
    if novo_saldo < -conta.limite_credito:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Saldo insuficiente. Saldo atual: R$ {conta.saldo}, "
                f"limite de crédito: R$ {conta.limite_credito}. Operação negada."
            ),
        )

    conta.saldo = novo_saldo
    _atualizar_data_saldo_negativo(conta, data_transacao)

    transacao = Transacao(
        conta_id=conta.id,
        tipo=TipoTransacao.SAQUE,
        valor=saque_in.valor,
        data=data_transacao,
        estado=EstadoTransacao.EFETIVADA,
        descricao=saque_in.descricao or "Saque em conta corrente",
    )
    db.add(transacao)
    db.commit()
    db.refresh(transacao)
    return transacao


def realizar_transferencia(db: Session, transf_in: TransferenciaCreate) -> Transacao:
    """
    Regra 1: Transferencia so e permitida em conta ativa, de cliente ativo.
    Regra 2: Saldo pode ficar negativo ate o limite de credito.
    Regra 3: Transferencia entre contas do mesmo cliente e isenta de tarifa.
             As demais consomem a franquia de transacoes isentas da categoria e, esgotada a franquia, geram tarifa.
    """
    conta_origem = db.query(Conta).filter(Conta.id == transf_in.conta_id).first()
    if not conta_origem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta de origem com ID {transf_in.conta_id} não encontrada."
        )

    conta_destino = db.query(Conta).filter(Conta.id == transf_in.conta_destino_id).first()
    if not conta_destino:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta de destino com ID {transf_in.conta_destino_id} não encontrada."
        )

    if conta_origem.estado != EstadoConta.ATIVA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transferências só são permitidas a partir de contas ativas. Estado atual: '{conta_origem.estado.value}'."
        )

    if conta_destino.estado != EstadoConta.ATIVA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A conta de destino não está ativa. Estado atual: '{conta_destino.estado.value}'."
        )

    cliente_origem = conta_origem.cliente
    if cliente_origem.situacao != SituacaoCliente.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transferências só são permitidas para clientes ativos. Situação atual: '{cliente_origem.situacao.value}'."
        )

    regras = REGRAS_CATEGORIAS[cliente_origem.categoria]

    # Verifica limite por transferência da categoria
    if transf_in.valor > regras.limite_por_transferencia:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Valor da transferência (R$ {transf_in.valor}) excede o limite por transferência "
                f"da categoria '{cliente_origem.categoria.value}' (R$ {regras.limite_por_transferencia})."
            ),
        )

    data_transacao = transf_in.data or get_current_time()

    # Regra 3: Checagem de tarifa
    mesmo_cliente = (conta_origem.cliente_id == conta_destino.cliente_id)
    tarifa_a_cobrar = Decimal("0.00")

    if not mesmo_cliente:
        # Se categoria tem franquia limitada
        if regras.transacoes_isentas_mes is not None:
            # Conta quantas transferências para outros clientes já foram feitas no mês corrente
            inicio_mes = datetime(data_transacao.year, data_transacao.month, 1)
            if data_transacao.month == 12:
                fim_mes = datetime(data_transacao.year + 1, 1, 1)
            else:
                fim_mes = datetime(data_transacao.year, data_transacao.month + 1, 1)

            # Contabiliza transferências efetivadas no mês para contas de outros clientes
            transfs_mes = (
                db.query(Transacao)
                .join(Conta, Transacao.conta_destino_id == Conta.id)
                .filter(
                    Transacao.conta_id == conta_origem.id,
                    Transacao.tipo == TipoTransacao.TRANSFERENCIA,
                    Transacao.estado == EstadoTransacao.EFETIVADA,
                    Transacao.data >= inicio_mes,
                    Transacao.data < fim_mes,
                    Conta.cliente_id != conta_origem.cliente_id,
                )
                .count()
            )

            if transfs_mes >= regras.transacoes_isentas_mes:
                tarifa_a_cobrar = VALOR_TARIFA_TRANSFERENCIA_PADRAO

    # Regra 2: Verifica saldo + limite de crédito na conta de origem
    custo_total = transf_in.valor + tarifa_a_cobrar
    novo_saldo_origem = conta_origem.saldo - custo_total
    if novo_saldo_origem < -conta_origem.limite_credito:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Saldo insuficiente na conta de origem. Saldo: R$ {conta_origem.saldo}, "
                f"limite de crédito: R$ {conta_origem.limite_credito}, "
                f"valor da operação (com tarifas se houver): R$ {custo_total}."
            ),
        )

    # Executa as movimentações
    conta_origem.saldo = novo_saldo_origem
    conta_destino.saldo += transf_in.valor

    _atualizar_data_saldo_negativo(conta_origem, data_transacao)
    _atualizar_data_saldo_negativo(conta_destino, data_transacao)

    # Registra a transferência
    transacao = Transacao(
        conta_id=conta_origem.id,
        conta_destino_id=conta_destino.id,
        tipo=TipoTransacao.TRANSFERENCIA,
        valor=transf_in.valor,
        data=data_transacao,
        estado=EstadoTransacao.EFETIVADA,
        descricao=transf_in.descricao or f"Transferência para conta {conta_destino.numero}",
    )
    db.add(transacao)

    # Registra a tarifa se aplicável
    if tarifa_a_cobrar > Decimal("0.00"):
        db_tarifa = Tarifa(
            conta_id=conta_origem.id,
            tipo=TipoTarifa.TRANSFERENCIA_EXCEDENTE.value,
            valor=tarifa_a_cobrar,
            data=data_transacao,
            estado=EstadoTarifa.COBRADA,
        )
        db.add(db_tarifa)

    db.commit()
    db.refresh(transacao)
    return transacao


def estornar_transacao(db: Session, transacao_id: int, motivo: Optional[str] = None) -> Transacao:
    """
    Regra 4: Uma transacao efetivada pode ser estornada em ate 24 horas.
    O estorno reverte o saldo das contas envolvidas e registra uma nova transacao do tipo estorno.
    """
    transacao = db.query(Transacao).filter(Transacao.id == transacao_id).first()
    if not transacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transação com ID {transacao_id} não encontrada."
        )

    if transacao.estado != EstadoTransacao.EFETIVADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Apenas transações efetivadas podem ser estornadas. Estado atual: '{transacao.estado.value}'."
        )

    if transacao.tipo == TipoTransacao.ESTORNO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível estornar uma transação de estorno."
        )

    agora = get_current_time()
    tempo_decorrido = agora - transacao.data
    horas_decorridas = tempo_decorrido.total_seconds() / 3600.0

    if horas_decorridas > LIMITE_HORAS_ESTORNO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Transação não pode ser estornada. O prazo limite é de {LIMITE_HORAS_ESTORNO} horas. "
                f"Tempo decorrido: {horas_decorridas:.1f} horas."
            ),
        )

    conta_origem = db.query(Conta).filter(Conta.id == transacao.conta_id).first()

    # Reverte os saldos
    if transacao.tipo == TipoTransacao.DEPOSITO:
        # Reverter depósito: subtrai o valor da conta
        if (conta_origem.saldo - transacao.valor) < -conta_origem.limite_credito:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível estornar o depósito: o saldo resultante ultrapassaria o limite de crédito."
            )
        conta_origem.saldo -= transacao.valor
        _atualizar_data_saldo_negativo(conta_origem, agora)

    elif transacao.tipo == TipoTransacao.SAQUE:
        # Reverter saque: devolve o valor para a conta
        conta_origem.saldo += transacao.valor
        _atualizar_data_saldo_negativo(conta_origem, agora)

    elif transacao.tipo == TipoTransacao.TRANSFERENCIA:
        # Reverter transferência: devolve o valor à origem e retira do destino
        conta_destino = db.query(Conta).filter(Conta.id == transacao.conta_destino_id).first()
        if not conta_destino:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conta de destino da transferência não encontrada para efetuar o estorno."
            )

        if (conta_destino.saldo - transacao.valor) < -conta_destino.limite_credito:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível estornar a transferência: a conta de destino não possui saldo/limite suficiente para o estorno."
            )

        conta_origem.saldo += transacao.valor
        conta_destino.saldo -= transacao.valor
        _atualizar_data_saldo_negativo(conta_origem, agora)
        _atualizar_data_saldo_negativo(conta_destino, agora)

    # Marca a transação original como estornada
    transacao.estado = EstadoTransacao.ESTORNADA

    # Cria nova transação do tipo estorno
    estorno_transacao = Transacao(
        conta_id=conta_origem.id,
        conta_destino_id=transacao.conta_destino_id,
        tipo=TipoTransacao.ESTORNO,
        valor=transacao.valor,
        data=agora,
        estado=EstadoTransacao.EFETIVADA,
        transacao_origem_id=transacao.id,
        descricao=motivo or f"Estorno da transação #{transacao.id} ({transacao.tipo.value})",
    )
    db.add(estorno_transacao)
    db.commit()
    db.refresh(estorno_transacao)
    return estorno_transacao


def obter_extrato(
    db: Session,
    conta_id: int,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
) -> ExtratoResponse:
    conta = db.query(Conta).filter(Conta.id == conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta com ID {conta_id} não encontrada."
        )

    query = db.query(Transacao).filter(
        or_(
            Transacao.conta_id == conta.id,
            Transacao.conta_destino_id == conta.id,
        )
    )

    if data_inicio:
        query = query.filter(Transacao.data >= data_inicio)
    if data_fim:
        query = query.filter(Transacao.data <= data_fim)

    transacoes = query.order_by(Transacao.data.desc(), Transacao.id.desc()).all()

    return ExtratoResponse(
        conta_id=conta.id,
        numero_conta=conta.numero,
        saldo_atual=conta.saldo,
        limite_credito=conta.limite_credito,
        transacoes=[TransacaoResponse.model_validate(t) for t in transacoes],
    )
