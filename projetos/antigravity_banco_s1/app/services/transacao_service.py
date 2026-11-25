from datetime import datetime, time, timezone
from decimal import Decimal
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.config import CATEGORY_RULES, settings
from app.models.cliente import SituacaoCliente
from app.models.conta import Conta, EstadoConta
from app.models.tarifa import EstadoTarifa, Tarifa
from app.models.transacao import EstadoTransacao, TipoTransacao, Transacao
from app.schemas.transacao import (
    DepositoCreate,
    ExtratoResponse,
    SaqueCreate,
    TransferenciaCreate,
)
from app.services.conta_service import ContaService


class TransacaoService:
    @staticmethod
    def _obter_regras_cliente(conta: Conta) -> dict:
        cliente = conta.cliente
        categoria_str = (
            cliente.categoria.value
            if hasattr(cliente.categoria, "value")
            else str(cliente.categoria)
        )
        return CATEGORY_RULES.get(categoria_str, CATEGORY_RULES["comum"])

    @staticmethod
    def realizar_deposito(db: Session, deposito_in: DepositoCreate) -> Transacao:
        conta = ContaService.obter_conta(db, deposito_in.conta_id)
        if conta.estado == EstadoConta.ENCERRADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível realizar depósito em conta encerrada.",
            )

        ContaService.ajustar_saldo_e_historico_negativo(conta, deposito_in.valor)

        transacao = Transacao(
            conta_id=conta.id,
            tipo=TipoTransacao.DEPOSITO,
            valor=deposito_in.valor,
            estado=EstadoTransacao.EFETIVADA,
            descricao=deposito_in.descricao or "Depósito em conta",
        )
        db.add(transacao)
        db.commit()
        db.refresh(transacao)
        return transacao

    @staticmethod
    def realizar_saque(db: Session, saque_in: SaqueCreate) -> Transacao:
        conta = ContaService.obter_conta(db, saque_in.conta_id)
        cliente = conta.cliente

        # Regra 1: Saque só é permitido em conta ativa, de cliente ativo
        if conta.estado != EstadoConta.ATIVA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Operação não permitida: conta #{conta.id} está no estado '{conta.estado.value}'.",
            )
        if cliente.situacao != SituacaoCliente.ATIVO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Operação não permitida: cliente #{cliente.id} está '{cliente.situacao.value}'.",
            )

        # Regra 1: Respeitar o limite diário acumulado da categoria
        regras = TransacaoService._obter_regras_cliente(conta)
        limite_diario = regras["limite_diario_saque"]

        agora = datetime.now(timezone.utc)
        inicio_do_dia = datetime.combine(agora.date(), time.min)
        fim_do_dia = datetime.combine(agora.date(), time.max)

        saques_hoje = (
            db.query(func.coalesce(func.sum(Transacao.valor), Decimal("0.00")))
            .filter(
                Transacao.conta_id == conta.id,
                Transacao.tipo == TipoTransacao.SAQUE,
                Transacao.estado == EstadoTransacao.EFETIVADA,
                Transacao.data >= inicio_do_dia,
                Transacao.data <= fim_do_dia,
            )
            .scalar()
        )

        if saques_hoje + saque_in.valor > limite_diario:
            disponivel = max(Decimal("0.00"), limite_diario - saques_hoje)
            categoria_str = cliente.categoria.value if hasattr(cliente.categoria, "value") else str(cliente.categoria)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Limite diário de saque excedido para a categoria {categoria_str.capitalize()}. "
                    f"Limite diário: R$ {limite_diario:.2f}. "
                    f"Já utilizado hoje: R$ {saques_hoje:.2f}. "
                    f"Disponível para saque hoje: R$ {disponivel:.2f}."
                ),
            )

        # Regra 2: Saldo pode ficar negativo até o limite de crédito
        saldo_disponivel = conta.saldo + conta.limite_credito
        if saldo_disponivel < saque_in.valor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Saldo insuficiente. Saldo disponível (incluindo limite de crédito): R$ {saldo_disponivel:.2f}. "
                    f"Valor solicitado: R$ {saque_in.valor:.2f}."
                ),
            )

        ContaService.ajustar_saldo_e_historico_negativo(conta, -saque_in.valor)

        transacao = Transacao(
            conta_id=conta.id,
            tipo=TipoTransacao.SAQUE,
            valor=saque_in.valor,
            estado=EstadoTransacao.EFETIVADA,
            descricao=saque_in.descricao or "Saque em conta",
        )
        db.add(transacao)
        db.commit()
        db.refresh(transacao)
        return transacao

    @staticmethod
    def realizar_transferencia(
        db: Session, transf_in: TransferenciaCreate
    ) -> Transacao:
        if transf_in.conta_origem_id == transf_in.conta_destino_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A conta de origem e a conta de destino não podem ser as mesmas.",
            )

        conta_origem = ContaService.obter_conta(db, transf_in.conta_origem_id)
        conta_destino = ContaService.obter_conta(db, transf_in.conta_destino_id)
        cliente_origem = conta_origem.cliente

        # Regra 1: Transferência só permitida em conta ativa, de cliente ativo
        if conta_origem.estado != EstadoConta.ATIVA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Conta de origem #{conta_origem.id} não está ativa.",
            )
        if cliente_origem.situacao != SituacaoCliente.ATIVO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cliente titular da conta de origem está '{cliente_origem.situacao.value}'.",
            )
        if conta_destino.estado != EstadoConta.ATIVA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Conta de destino #{conta_destino.id} não está ativa.",
            )

        # Regra 1: Limite por transferência da categoria
        regras = TransacaoService._obter_regras_cliente(conta_origem)
        limite_por_transferencia = regras["limite_por_transferencia"]
        if transf_in.valor > limite_por_transferencia:
            categoria_str = (
                cliente_origem.categoria.value
                if hasattr(cliente_origem.categoria, "value")
                else str(cliente_origem.categoria)
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Limite por transferência excedido para a categoria {categoria_str.capitalize()}. "
                    f"Máximo permitido por operação: R$ {limite_por_transferencia:.2f}."
                ),
            )

        # Regra 3: Transferência entre contas do mesmo cliente é isenta de tarifa.
        # As demais consomem a franquia de transações isentas da categoria e, esgotada a franquia, geram tarifa.
        mesmo_cliente = conta_origem.cliente_id == conta_destino.cliente_id
        tarifa_cobrada = Decimal("0.00")
        tarifa_obj = None

        if not mesmo_cliente:
            agora = datetime.now(timezone.utc)
            franquia_isenta = regras["transacoes_isentas_mes"]

            # Contabiliza transferências para contas de terceiros no mês atual
            transferencias_no_mes = (
                db.query(Transacao)
                .join(Conta, Transacao.conta_destino_id == Conta.id)
                .filter(
                    Transacao.conta_id == conta_origem.id,
                    Transacao.tipo == TipoTransacao.TRANSFERENCIA,
                    Transacao.estado == EstadoTransacao.EFETIVADA,
                    extract("year", Transacao.data) == agora.year,
                    extract("month", Transacao.data) == agora.month,
                    Conta.cliente_id != conta_origem.cliente_id,
                )
                .count()
            )

            if transferencias_no_mes >= franquia_isenta:
                tarifa_cobrada = settings.TARIFA_TRANSFERENCIA_PADRAO
            else:
                # Registra tarifa isenta para histórico e controle
                tarifa_obj = Tarifa(
                    conta_id=conta_origem.id,
                    tipo="transferencia",
                    valor=Decimal("0.00"),
                    estado=EstadoTarifa.ISENTA,
                    descricao="Transferência isenta (franquia mensal)",
                )

        # Regra 2: Saldo pode ficar negativo até o limite de crédito (considerando valor + tarifa)
        valor_total_debito = transf_in.valor + tarifa_cobrada
        saldo_disponivel = conta_origem.saldo + conta_origem.limite_credito
        if saldo_disponivel < valor_total_debito:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Saldo insuficiente na conta de origem para cobrir a transferência e tarifa. "
                    f"Necessário: R$ {valor_total_debito:.2f} (Transferência: R$ {transf_in.valor:.2f} + Tarifa: R$ {tarifa_cobrada:.2f}). "
                    f"Disponível: R$ {saldo_disponivel:.2f}."
                ),
            )

        # Debita valor e tarifa da conta origem
        ContaService.ajustar_saldo_e_historico_negativo(conta_origem, -transf_in.valor)
        if tarifa_cobrada > Decimal("0.00"):
            ContaService.ajustar_saldo_e_historico_negativo(conta_origem, -tarifa_cobrada)
            tarifa_obj = Tarifa(
                conta_id=conta_origem.id,
                tipo="transferencia",
                valor=tarifa_cobrada,
                estado=EstadoTarifa.COBRADA,
                descricao="Tarifa de transferência (franquia mensal excedida)",
            )

        if tarifa_obj:
            db.add(tarifa_obj)

        # Credita na conta destino
        ContaService.ajustar_saldo_e_historico_negativo(conta_destino, transf_in.valor)

        transacao = Transacao(
            conta_id=conta_origem.id,
            conta_destino_id=conta_destino.id,
            tipo=TipoTransacao.TRANSFERENCIA,
            valor=transf_in.valor,
            estado=EstadoTransacao.EFETIVADA,
            descricao=transf_in.descricao or f"Transferência para conta #{conta_destino.numero}",
        )
        db.add(transacao)
        db.commit()
        db.refresh(transacao)
        return transacao

    @staticmethod
    def estornar_transacao(db: Session, transacao_id: int) -> Transacao:
        """
        Regra 4: Uma transação efetivada pode ser estornada em até 24 horas.
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
                detail=f"Apenas transações efetivadas podem ser estornadas. Estado atual: '{transacao.estado.value}'.",
            )

        if transacao.tipo == TipoTransacao.ESTORNO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível realizar o estorno de uma transação de estorno.",
            )

        # Verifica janela de 24 horas
        agora = datetime.now(timezone.utc)
        data_tx = (
            transacao.data
            if transacao.data.tzinfo is not None
            else transacao.data.replace(tzinfo=timezone.utc)
        )
        diferenca_segundos = (agora - data_tx).total_seconds()
        if diferenca_segundos > 24 * 3600:
            horas_passadas = diferenca_segundos / 3600
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A transação só pode ser estornada em até 24 horas. Tempo decorrido: {horas_passadas:.1f} horas.",
            )

        conta_origem = transacao.conta
        conta_destino = transacao.conta_destino

        # Reversão de saldos conforme o tipo
        if transacao.tipo == TipoTransacao.DEPOSITO:
            # Depósito aumentou o saldo da conta. O estorno reduz o saldo da conta.
            # Verifica se a conta suporta a dedução até o limite de crédito (Regra 2)
            saldo_disponivel = conta_origem.saldo + conta_origem.limite_credito
            if saldo_disponivel < transacao.valor:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Conta não possui saldo/limite suficiente para estorno do depósito. Disponível: R$ {saldo_disponivel:.2f}.",
                )
            ContaService.ajustar_saldo_e_historico_negativo(conta_origem, -transacao.valor)

        elif transacao.tipo == TipoTransacao.SAQUE:
            # Saque reduziu o saldo da conta. O estorno devolve o saldo.
            ContaService.ajustar_saldo_e_historico_negativo(conta_origem, transacao.valor)

        elif transacao.tipo == TipoTransacao.TRANSFERENCIA:
            # Transferência debitou da origem e creditou no destino.
            # O estorno reverte: deduz do destino e credita de volta na origem.
            if not conta_destino:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Conta de destino não identificada para o estorno.",
                )
            saldo_disponivel_destino = conta_destino.saldo + conta_destino.limite_credito
            if saldo_disponivel_destino < transacao.valor:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Conta de destino não possui saldo suficiente para reverter a transferência. Disponível: R$ {saldo_disponivel_destino:.2f}.",
                )

            ContaService.ajustar_saldo_e_historico_negativo(conta_destino, -transacao.valor)
            ContaService.ajustar_saldo_e_historico_negativo(conta_origem, transacao.valor)

        # Atualiza a transação original para ESTORNADA
        transacao.estado = EstadoTransacao.ESTORNADA

        # Registra a nova transação do tipo ESTORNO
        estorno_transacao = Transacao(
            conta_id=transacao.conta_id,
            conta_destino_id=transacao.conta_destino_id,
            tipo=TipoTransacao.ESTORNO,
            valor=transacao.valor,
            estado=EstadoTransacao.EFETIVADA,
            transacao_origem_id=transacao.id,
            descricao=f"Estorno da transação #{transacao.id} ({transacao.tipo.value})",
        )
        db.add(estorno_transacao)
        db.commit()
        db.refresh(estorno_transacao)
        return estorno_transacao

    @staticmethod
    def obter_extrato(
        db: Session,
        conta_id: int,
        data_inicio: Optional[datetime] = None,
        data_fim: Optional[datetime] = None,
        tipo: Optional[str] = None,
    ) -> ExtratoResponse:
        conta = ContaService.obter_conta(db, conta_id)
        query = db.query(Transacao).filter(
            (Transacao.conta_id == conta_id) | (Transacao.conta_destino_id == conta_id)
        )

        if data_inicio:
            query = query.filter(Transacao.data >= data_inicio)
        if data_fim:
            query = query.filter(Transacao.data <= data_fim)
        if tipo:
            query = query.filter(Transacao.tipo == tipo)

        transacoes = query.order_by(Transacao.data.desc()).all()

        return ExtratoResponse(
            conta_id=conta.id,
            numero_conta=conta.numero,
            cliente_nome=conta.cliente.nome,
            saldo_atual=conta.saldo,
            limite_credito=conta.limite_credito,
            saldo_disponivel=conta.saldo + conta.limite_credito,
            total_transacoes=len(transacoes),
            transacoes=transacoes,
        )
