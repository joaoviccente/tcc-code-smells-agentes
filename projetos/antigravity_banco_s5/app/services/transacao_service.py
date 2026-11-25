from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import HTTPException, status
from app.models.transacao import Transacao
from app.models.conta import Conta
from app.models.tarifa import Tarifa
from app.schemas.transacao import (
    DepositoRequest,
    SaqueRequest,
    TransferenciaRequest,
    ExtratoResponse,
    TransacaoResponse,
)
from app.config import (
    TipoTransacao,
    EstadoTransacao,
    EstadoConta,
    SituacaoCliente,
    TipoTarifa,
    EstadoTarifa,
    REGRAS_CATEGORIA,
    VALOR_TARIFA_TRANSFERENCIA,
    HORAS_LIMITE_ESTORNO,
)
from app.services.conta_service import ajustar_rastreamento_saldo_negativo
from app.utils import utc_now


def realizar_deposito(db: Session, req: DepositoRequest) -> Transacao:
    conta = db.query(Conta).filter(Conta.id == req.conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta #{req.conta_id} não encontrada.",
        )
    if conta.estado == EstadoConta.ENCERRADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível realizar depósito em uma conta encerrada.",
        )

    # Creditar saldo
    conta.saldo += req.valor
    ajustar_rastreamento_saldo_negativo(conta)

    transacao = Transacao(
        conta_id=conta.id,
        tipo=TipoTransacao.DEPOSITO,
        valor=req.valor,
        data=utc_now(),
        estado=EstadoTransacao.EFETIVADA,
        descricao=req.descricao or "Depósito em conta",
    )
    db.add(transacao)
    db.commit()
    db.refresh(transacao)
    return transacao


def realizar_saque(db: Session, req: SaqueRequest) -> Transacao:
    conta = db.query(Conta).filter(Conta.id == req.conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta #{req.conta_id} não encontrada.",
        )

    # Regra 1: Saque e transferência só são permitidos em conta ativa, de cliente ativo
    if conta.estado != EstadoConta.ATIVA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Operação negada: a conta #{conta.id} não está ativa (estado: {conta.estado.value}).",
        )
    if conta.cliente.situacao != SituacaoCliente.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Operação negada: o titular da conta está bloqueado.",
        )

    # Regra 1: Respeitar o limite diário acumulado da categoria
    regras = REGRAS_CATEGORIA[conta.cliente.categoria]
    limite_diario_saque = regras["limite_diario_saque"]

    hoje_inicio = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    hoje_fim = utc_now().replace(hour=23, minute=59, second=59, microsecond=999999)

    saques_hoje = (
        db.query(Transacao)
        .filter(
            Transacao.conta_id == conta.id,
            Transacao.tipo == TipoTransacao.SAQUE,
            Transacao.estado == EstadoTransacao.EFETIVADA,
            Transacao.data >= hoje_inicio,
            Transacao.data <= hoje_fim,
        )
        .all()
    )
    total_sacado_hoje = sum((s.valor for s in saques_hoje), Decimal("0.00"))

    if total_sacado_hoje + req.valor > limite_diario_saque:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Limite diário de saque excedido para a categoria {conta.cliente.categoria.value}. "
                f"Limite diário: R$ {limite_diario_saque:.2f}, já sacado hoje: R$ {total_sacado_hoje:.2f}, "
                f"tentativa: R$ {req.valor:.2f}."
            ),
        )

    # Regra 2: O saldo pode ficar negativo até o limite de crédito da conta.
    saldo_disponivel = conta.saldo + conta.limite_credito
    if saldo_disponivel < req.valor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Saldo insuficiente. Saldo disponível (incluindo limite de crédito): "
                f"R$ {saldo_disponivel:.2f}, valor do saque: R$ {req.valor:.2f}."
            ),
        )

    # Executar saque
    conta.saldo -= req.valor
    ajustar_rastreamento_saldo_negativo(conta)

    transacao = Transacao(
        conta_id=conta.id,
        tipo=TipoTransacao.SAQUE,
        valor=req.valor,
        data=utc_now(),
        estado=EstadoTransacao.EFETIVADA,
        descricao=req.descricao or "Saque em conta",
    )
    db.add(transacao)
    db.commit()
    db.refresh(transacao)
    return transacao


def realizar_transferencia(db: Session, req: TransferenciaRequest) -> Transacao:
    if req.conta_origem_id == req.conta_destino_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A conta de origem e a conta de destino não podem ser as mesmas.",
        )

    conta_origem = db.query(Conta).filter(Conta.id == req.conta_origem_id).first()
    if not conta_origem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta de origem #{req.conta_origem_id} não encontrada.",
        )

    conta_destino = db.query(Conta).filter(Conta.id == req.conta_destino_id).first()
    if not conta_destino:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta de destino #{req.conta_destino_id} não encontrada.",
        )

    # Regra 1: Saque e transferência só são permitidos em conta ativa, de cliente ativo
    if conta_origem.estado != EstadoConta.ATIVA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Operação negada: a conta de origem #{conta_origem.id} não está ativa (estado: {conta_origem.estado.value}).",
        )
    if conta_origem.cliente.situacao != SituacaoCliente.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Operação negada: o titular da conta de origem está bloqueado.",
        )

    if conta_destino.estado == EstadoConta.ENCERRADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A conta de destino #{conta_destino.id} está encerrada.",
        )

    # Regra da Categoria: limite por transferência
    regras = REGRAS_CATEGORIA[conta_origem.cliente.categoria]
    limite_por_transferencia = regras["limite_por_transferencia"]
    if req.valor > limite_por_transferencia:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Valor da transferência excede o limite por operação da categoria {conta_origem.cliente.categoria.value}. "
                f"Limite permitido: R$ {limite_por_transferencia:.2f}, solicitado: R$ {req.valor:.2f}."
            ),
        )

    # Regra 3: Transferência entre contas do mesmo cliente é isenta de tarifa.
    # As demais consomem a franquia de transações isentas da categoria e, esgotada a franquia, geram tarifa.
    mesmo_cliente = conta_origem.cliente_id == conta_destino.cliente_id
    valor_tarifa = Decimal("0.00")
    tarifa_estado = EstadoTarifa.ISENTA

    if not mesmo_cliente:
        franquia_isenta = regras["transacoes_isentas_mes"]
        if franquia_isenta is not None:
            # Contar transferências realizadas neste mês por esta conta para outros clientes
            agora = utc_now()
            inicio_mes = datetime(agora.year, agora.month, 1)

            transacoes_mes = (
                db.query(Transacao)
                .join(Conta, Conta.id == Transacao.conta_destino_id)
                .filter(
                    Transacao.conta_id == conta_origem.id,
                    Transacao.tipo == TipoTransacao.TRANSFERENCIA,
                    Transacao.estado == EstadoTransacao.EFETIVADA,
                    Transacao.data >= inicio_mes,
                    Conta.cliente_id != conta_origem.cliente_id,
                )
                .count()
            )

            if transacoes_mes >= franquia_isenta:
                valor_tarifa = VALOR_TARIFA_TRANSFERENCIA
                tarifa_estado = EstadoTarifa.COBRADA

    # Regra 2: O saldo pode ficar negativo até o limite de crédito da conta.
    total_a_debitar = req.valor + valor_tarifa
    saldo_disponivel = conta_origem.saldo + conta_origem.limite_credito
    if saldo_disponivel < total_a_debitar:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Saldo insuficiente. Saldo disponível: R$ {saldo_disponivel:.2f}, "
                f"valor necessário (transferência de R$ {req.valor:.2f} + tarifa de R$ {valor_tarifa:.2f}): "
                f"R$ {total_a_debitar:.2f}."
            ),
        )

    # Realizar débitos e créditos
    conta_origem.saldo -= total_a_debitar
    conta_destino.saldo += req.valor

    ajustar_rastreamento_saldo_negativo(conta_origem)
    ajustar_rastreamento_saldo_negativo(conta_destino)

    # Registrar Tarifa
    tarifa = Tarifa(
        conta_id=conta_origem.id,
        tipo=TipoTarifa.TRANSFERENCIA_EXCEDENTE,
        valor=valor_tarifa,
        estado=tarifa_estado,
        data=utc_now(),
    )
    db.add(tarifa)

    # Registrar Transação
    transacao = Transacao(
        conta_id=conta_origem.id,
        conta_destino_id=conta_destino.id,
        tipo=TipoTransacao.TRANSFERENCIA,
        valor=req.valor,
        data=utc_now(),
        estado=EstadoTransacao.EFETIVADA,
        descricao=req.descricao or f"Transferência para conta {conta_destino.numero}",
    )
    db.add(transacao)
    db.commit()
    db.refresh(transacao)
    return transacao


def estornar_transacao(db: Session, transacao_id: int) -> Transacao:
    """
    Regra de Negócio 4:
    Uma transação efetivada pode ser estornada em até 24 horas.
    O estorno reverte o saldo das contas envolvidas e registra uma nova transação do tipo estorno.
    """
    transacao = db.query(Transacao).filter(Transacao.id == transacao_id).first()
    if not transacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transação #{transacao_id} não encontrada.",
        )

    if transacao.estado != EstadoTransacao.EFETIVADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Apenas transações efetivadas podem ser estornadas. Estado atual: {transacao.estado.value}.",
        )

    if transacao.tipo == TipoTransacao.ESTORNO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível estornar uma transação de estorno.",
        )

    tempo_decorrido = utc_now() - transacao.data
    if tempo_decorrido > timedelta(hours=HORAS_LIMITE_ESTORNO):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O prazo máximo para estorno é de {HORAS_LIMITE_ESTORNO} horas. Tempo decorrido: {tempo_decorrido}.",
        )

    conta_origem = transacao.conta

    if transacao.tipo == TipoTransacao.DEPOSITO:
        # Reversão do depósito: debitar o valor da conta
        saldo_disponivel = conta_origem.saldo + conta_origem.limite_credito
        if saldo_disponivel < transacao.valor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A conta não possui saldo/limite suficiente para o estorno do depósito.",
            )
        conta_origem.saldo -= transacao.valor
        ajustar_rastreamento_saldo_negativo(conta_origem)

    elif transacao.tipo == TipoTransacao.SAQUE:
        # Reversão do saque: creditar o valor de volta na conta
        conta_origem.saldo += transacao.valor
        ajustar_rastreamento_saldo_negativo(conta_origem)

    elif transacao.tipo == TipoTransacao.TRANSFERENCIA:
        # Reversão da transferência: debitar da conta destino e creditar na origem
        conta_destino = transacao.conta_destino
        if not conta_destino:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Conta de destino não identificada para o estorno.",
            )

        saldo_disponivel_destino = conta_destino.saldo + conta_destino.limite_credito
        if saldo_disponivel_destino < transacao.valor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A conta de destino não possui saldo/limite suficiente para a devolução do estorno.",
            )

        conta_destino.saldo -= transacao.valor
        conta_origem.saldo += transacao.valor
        ajustar_rastreamento_saldo_negativo(conta_destino)
        ajustar_rastreamento_saldo_negativo(conta_origem)

    # Atualizar o estado da transação original para estornada
    transacao.estado = EstadoTransacao.ESTORNADA

    # Criar nova transação do tipo estorno
    estorno = Transacao(
        conta_id=transacao.conta_id,
        conta_destino_id=transacao.conta_destino_id,
        tipo=TipoTransacao.ESTORNO,
        valor=transacao.valor,
        data=utc_now(),
        estado=EstadoTransacao.EFETIVADA,
        transacao_origem_id=transacao.id,
        descricao=f"Estorno referente à transação #{transacao.id} ({transacao.tipo.value})",
    )
    db.add(estorno)
    db.commit()
    db.refresh(estorno)
    return estorno


def obter_extrato_conta(
    db: Session,
    conta_id: int,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
) -> ExtratoResponse:
    conta = db.query(Conta).filter(Conta.id == conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta #{conta_id} não encontrada.",
        )

    # Transações onde a conta é origem ou destino
    query = db.query(Transacao).filter(
        or_(Transacao.conta_id == conta.id, Transacao.conta_destino_id == conta.id)
    )

    if data_inicio:
        query = query.filter(Transacao.data >= data_inicio)
    if data_fim:
        query = query.filter(Transacao.data <= data_fim)

    transacoes = query.order_by(Transacao.data.asc()).all()

    return ExtratoResponse(
        conta_id=conta.id,
        numero_conta=conta.numero,
        cliente_nome=conta.cliente.nome,
        saldo_atual=conta.saldo,
        limite_credito=conta.limite_credito,
        saldo_disponivel=conta.saldo + conta.limite_credito,
        transacoes=[TransacaoResponse.model_validate(t) for t in transacoes],
    )
