from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
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
    EstadoConta,
    SituacaoCliente,
    TipoTransacao,
    EstadoTransacao,
    TipoTarifa,
    EstadoTarifa,
    REGRAS_CATEGORIA,
    VALOR_TARIFA_TRANSFERENCIA_EXCEDENTE,
)


class TransacaoService:
    @staticmethod
    def get_by_id(db: Session, transacao_id: int) -> Transacao:
        transacao = db.query(Transacao).filter(Transacao.id == transacao_id).first()
        if not transacao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transação com ID {transacao_id} não encontrada.",
            )
        return transacao

    @staticmethod
    def list(
        db: Session,
        conta_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Transacao]:
        query = db.query(Transacao)
        if conta_id:
            query = query.filter(
                (Transacao.conta_id == conta_id) | (Transacao.conta_destino_id == conta_id)
            )
        return query.order_by(Transacao.data.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def deposito(db: Session, req: DepositoRequest) -> Transacao:
        conta = db.query(Conta).filter(Conta.id == req.conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {req.conta_id} não encontrada.",
            )

        if conta.estado == EstadoConta.ENCERRADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível realizar depósito em uma conta encerrada.",
            )

        # Atualiza saldo
        conta.saldo += req.valor
        if conta.saldo >= Decimal("0.00"):
            conta.saldo_negativo_desde = None

        transacao = Transacao(
            conta_id=conta.id,
            tipo=TipoTransacao.DEPOSITO,
            valor=req.valor,
            estado=EstadoTransacao.EFETIVADA,
            descricao=req.descricao or "Depósito em conta corrente",
        )
        db.add(transacao)
        db.commit()
        db.refresh(transacao)
        return transacao

    @staticmethod
    def saque(db: Session, req: SaqueRequest) -> Transacao:
        conta = db.query(Conta).filter(Conta.id == req.conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {req.conta_id} não encontrada.",
            )

        # Regra 1: Saque só é permitido em conta ativa, de cliente ativo
        if conta.estado != EstadoConta.ATIVA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Saque não permitido: conta encontra-se '{conta.estado.value}'.",
            )

        cliente = conta.cliente
        if cliente.situacao != SituacaoCliente.ATIVO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Saque não permitido: cliente titular encontra-se '{cliente.situacao.value}'.",
            )

        # Regra 1: respeitando o limite diário acumulado da categoria
        regras = REGRAS_CATEGORIA[cliente.categoria]
        limite_diario = regras["limite_diario_saque"]

        # Calcula saques realizados hoje (dia civil corrente)
        hoje_inicio = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        total_sacado_hoje = (
            db.query(func.coalesce(func.sum(Transacao.valor), 0))
            .filter(
                Transacao.conta_id == conta.id,
                Transacao.tipo == TipoTransacao.SAQUE,
                Transacao.estado == EstadoTransacao.EFETIVADA,
                Transacao.data >= hoje_inicio,
            )
            .scalar()
        )
        total_sacado_hoje = Decimal(str(total_sacado_hoje))

        if total_sacado_hoje + req.valor > limite_diario:
            disponivel_hoje = max(Decimal("0.00"), limite_diario - total_sacado_hoje)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Limite diário de saque excedido para a categoria '{cliente.categoria.value}'. "
                    f"Limite diário: R$ {limite_diario:.2f}, Já sacado hoje: R$ {total_sacado_hoje:.2f}, "
                    f"Disponível para saque hoje: R$ {disponivel_hoje:.2f}."
                ),
            )

        # Regra 2: O saldo pode ficar negativo até o limite de crédito da conta. Abaixo disso, a operação é negada.
        disponivel_conta = conta.saldo + conta.limite_credito
        if req.valor > disponivel_conta:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Saldo insuficiente para saque. Saldo: R$ {conta.saldo:.2f}, "
                    f"Limite de crédito: R$ {conta.limite_credito:.2f}, "
                    f"Total disponível: R$ {disponivel_conta:.2f}."
                ),
            )

        conta.saldo -= req.valor
        if conta.saldo < Decimal("0.00") and conta.saldo_negativo_desde is None:
            conta.saldo_negativo_desde = datetime.now(timezone.utc)

        transacao = Transacao(
            conta_id=conta.id,
            tipo=TipoTransacao.SAQUE,
            valor=req.valor,
            estado=EstadoTransacao.EFETIVADA,
            descricao=req.descricao or "Saque em conta corrente",
        )
        db.add(transacao)
        db.commit()
        db.refresh(transacao)
        return transacao

    @staticmethod
    def transferencia(db: Session, req: TransferenciaRequest) -> Transacao:
        if req.conta_origem_id == req.conta_destino_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A conta de origem e a conta de destino não podem ser iguais.",
            )

        conta_origem = db.query(Conta).filter(Conta.id == req.conta_origem_id).first()
        if not conta_origem:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta de origem com ID {req.conta_origem_id} não encontrada.",
            )

        conta_destino = db.query(Conta).filter(Conta.id == req.conta_destino_id).first()
        if not conta_destino:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta de destino com ID {req.conta_destino_id} não encontrada.",
            )

        # Regra 1: Saque e transferência só são permitidos em conta ativa, de cliente ativo
        if conta_origem.estado != EstadoConta.ATIVA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transferência não permitida: conta de origem encontra-se '{conta_origem.estado.value}'.",
            )

        cliente_origem = conta_origem.cliente
        if cliente_origem.situacao != SituacaoCliente.ATIVO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transferência não permitida: cliente titular de origem encontra-se '{cliente_origem.situacao.value}'.",
            )

        if conta_destino.estado != EstadoConta.ATIVA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transferência não permitida: conta de destino encontra-se '{conta_destino.estado.value}'.",
            )

        # Limite por transferência da categoria
        regras = REGRAS_CATEGORIA[cliente_origem.categoria]
        limite_transferencia = regras["limite_por_transferencia"]
        if req.valor > limite_transferencia:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Limite por transferência excedido para a categoria '{cliente_origem.categoria.value}'. "
                    f"Limite por operação: R$ {limite_transferencia:.2f}, Valor solicitado: R$ {req.valor:.2f}."
                ),
            )

        # Regra 3: Transferência entre contas do mesmo cliente é isenta de tarifa.
        # As demais consomem a franquia de transações isentas da categoria e, esgotada a franquia, geram tarifa.
        mesmo_cliente = conta_origem.cliente_id == conta_destino.cliente_id
        tarifa_a_cobrar = Decimal("0.00")
        tarifa_isenta = True

        if mesmo_cliente:
            tarifa_isenta = True
            tarifa_a_cobrar = Decimal("0.00")
        else:
            franquia = regras["transacoes_isentas_mes"]
            if franquia is None:
                # Premium: transações isentas ilimitadas
                tarifa_isenta = True
                tarifa_a_cobrar = Decimal("0.00")
            else:
                # Calcula transferências para terceiros feitas no mês atual
                agora = datetime.now(timezone.utc)
                mes_inicio = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

                # Conta transferências já realizadas neste mês para terceiros
                transferencias_terceiros_mes = (
                    db.query(Transacao)
                    .join(Conta, Transacao.conta_destino_id == Conta.id)
                    .filter(
                        Transacao.conta_id == conta_origem.id,
                        Transacao.tipo == TipoTransacao.TRANSFERENCIA,
                        Transacao.estado == EstadoTransacao.EFETIVADA,
                        Transacao.data >= mes_inicio,
                        Conta.cliente_id != conta_origem.cliente_id,
                    )
                    .count()
                )

                if transferencias_terceiros_mes < franquia:
                    tarifa_isenta = True
                    tarifa_a_cobrar = Decimal("0.00")
                else:
                    tarifa_isenta = False
                    tarifa_a_cobrar = VALOR_TARIFA_TRANSFERENCIA_EXCEDENTE

        # Regra 2: Saldo pode ficar negativo até limite de crédito
        total_debito = req.valor + tarifa_a_cobrar
        disponivel_origem = conta_origem.saldo + conta_origem.limite_credito
        if total_debito > disponivel_origem:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Saldo insuficiente para transferência. Valor: R$ {req.valor:.2f}, "
                    f"Tarifa: R$ {tarifa_a_cobrar:.2f}, Total: R$ {total_debito:.2f}, "
                    f"Disponível na conta de origem: R$ {disponivel_origem:.2f}."
                ),
            )

        # Atualiza saldos
        conta_origem.saldo -= total_debito
        if conta_origem.saldo < Decimal("0.00") and conta_origem.saldo_negativo_desde is None:
            conta_origem.saldo_negativo_desde = datetime.now(timezone.utc)

        conta_destino.saldo += req.valor
        if conta_destino.saldo >= Decimal("0.00"):
            conta_destino.saldo_negativo_desde = None

        # Registra transação de transferência
        transacao = Transacao(
            conta_id=conta_origem.id,
            conta_destino_id=conta_destino.id,
            tipo=TipoTransacao.TRANSFERENCIA,
            valor=req.valor,
            estado=EstadoTransacao.EFETIVADA,
            descricao=req.descricao
            or f"Transferência para conta {conta_destino.numero}",
        )
        db.add(transacao)

        # Registra registro de Tarifa
        tarifa = Tarifa(
            conta_id=conta_origem.id,
            tipo=TipoTarifa.TRANSFERENCIA,
            valor=tarifa_a_cobrar,
            estado=EstadoTarifa.ISENTA if tarifa_isenta else EstadoTarifa.COBRADA,
            data=datetime.now(timezone.utc),
        )
        db.add(tarifa)

        db.commit()
        db.refresh(transacao)
        return transacao

    @staticmethod
    def estorno(db: Session, transacao_id: int) -> Transacao:
        """
        Regra 4: Uma transação efetivada pode ser estornada em até 24 horas.
        O estorno reverte o saldo das contas envolvidas e registra uma nova transação do tipo estorno.
        """
        transacao_orig = TransacaoService.get_by_id(db, transacao_id)

        if transacao_orig.estado != EstadoTransacao.EFETIVADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Apenas transações efetivadas podem ser estornadas. Estado atual: '{transacao_orig.estado.value}'.",
            )

        if transacao_orig.tipo == TipoTransacao.ESTORNO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível realizar estorno de uma transação de estorno.",
            )

        # Verifica limite de 24 horas
        data_tx = transacao_orig.data
        if data_tx.tzinfo is None:
            data_tx = data_tx.replace(tzinfo=timezone.utc)
        agora = datetime.now(timezone.utc)

        if agora - data_tx > timedelta(hours=24):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A transação não pode ser estornada após 24 horas da sua realização.",
            )

        conta_origem = db.query(Conta).filter(Conta.id == transacao_orig.conta_id).first()

        # Reverte os saldos conforme o tipo da transação original
        if transacao_orig.tipo == TipoTransacao.DEPOSITO:
            # Estorno de depósito: retira o valor da conta
            disponivel = conta_origem.saldo + conta_origem.limite_credito
            if transacao_orig.valor > disponivel:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Não é possível estornar o depósito: a conta não possui saldo/limite de crédito suficiente para a reversão.",
                )
            conta_origem.saldo -= transacao_orig.valor
            if conta_origem.saldo < Decimal("0.00") and conta_origem.saldo_negativo_desde is None:
                conta_origem.saldo_negativo_desde = datetime.now(timezone.utc)

        elif transacao_orig.tipo == TipoTransacao.SAQUE:
            # Estorno de saque: devolve o valor para a conta
            conta_origem.saldo += transacao_orig.valor
            if conta_origem.saldo >= Decimal("0.00"):
                conta_origem.saldo_negativo_desde = None

        elif transacao_orig.tipo == TipoTransacao.TRANSFERENCIA:
            # Estorno de transferência: devolve para origem e retira do destino
            conta_destino = db.query(Conta).filter(Conta.id == transacao_orig.conta_destino_id).first()
            if not conta_destino:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conta de destino da transferência não encontrada para efetuar o estorno.",
                )

            disponivel_destino = conta_destino.saldo + conta_destino.limite_credito
            if transacao_orig.valor > disponivel_destino:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Não é possível estornar a transferência: a conta destinatária não possui saldo/limite suficiente para a devolução.",
                )

            conta_destino.saldo -= transacao_orig.valor
            if conta_destino.saldo < Decimal("0.00") and conta_destino.saldo_negativo_desde is None:
                conta_destino.saldo_negativo_desde = datetime.now(timezone.utc)

            conta_origem.saldo += transacao_orig.valor
            if conta_origem.saldo >= Decimal("0.00"):
                conta_origem.saldo_negativo_desde = None

        # Marca a transação original como estornada
        transacao_orig.estado = EstadoTransacao.ESTORNADA

        # Registra a nova transação do tipo estorno
        nova_transacao = Transacao(
            conta_id=transacao_orig.conta_id,
            conta_destino_id=transacao_orig.conta_destino_id,
            transacao_origem_id=transacao_orig.id,
            tipo=TipoTransacao.ESTORNO,
            valor=transacao_orig.valor,
            estado=EstadoTransacao.EFETIVADA,
            descricao=f"Estorno da transação #{transacao_orig.id} ({transacao_orig.tipo.value})",
        )
        db.add(nova_transacao)
        db.commit()
        db.refresh(nova_transacao)
        return nova_transacao

    @staticmethod
    def extrato(
        db: Session,
        conta_id: int,
        data_inicio: Optional[datetime] = None,
        data_fim: Optional[datetime] = None,
    ) -> ExtratoResponse:
        conta = db.query(Conta).filter(Conta.id == conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {conta_id} não encontrada.",
            )

        query = db.query(Transacao).filter(
            (Transacao.conta_id == conta_id) | (Transacao.conta_destino_id == conta_id)
        )
        if data_inicio:
            query = query.filter(Transacao.data >= data_inicio)
        if data_fim:
            query = query.filter(Transacao.data <= data_fim)

        transacoes = query.order_by(Transacao.data.asc()).all()

        return ExtratoResponse(
            conta_id=conta.id,
            numero_conta=conta.numero,
            saldo_atual=conta.saldo,
            limite_credito=conta.limite_credito,
            total_disponivel=conta.saldo + conta.limite_credito,
            transacoes=[TransacaoResponse.model_validate(t) for t in transacoes],
        )
