from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from fastapi import HTTPException, status

from app.config import settings
from app.models.transacao import Transacao
from app.models.conta import Conta
from app.models.tarifa import Tarifa
from app.models.enums import (
    TipoTransacao,
    EstadoTransacao,
    EstadoConta,
    EstadoTarifa,
    SituacaoCliente,
)
from app.schemas.transacao import (
    DepositoRequest,
    SaqueRequest,
    TransferenciaRequest,
    ExtratoResponse,
    TransacaoResponse,
)
from app.services.regras_categoria import RegrasCategoriaService


class TransacaoService:
    @staticmethod
    def _verificar_saldo_disponivel(conta: Conta, valor_a_debitar: Decimal) -> None:
        """Regra 2: O saldo pode ficar negativo até o limite de crédito da conta. Abaixo disso, é negado."""
        saldo_disponivel = Decimal(str(conta.saldo)) + Decimal(str(conta.limite_de_credito))
        if saldo_disponivel < valor_a_debitar:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Saldo insuficiente para realizar a operação. "
                    f"Disponível (saldo + limite de crédito): R$ {saldo_disponivel:.2f}, "
                    f"Necessário: R$ {valor_a_debitar:.2f}."
                ),
            )

    @staticmethod
    def _atualizar_data_saldo_negativo(conta: Conta) -> None:
        """Regra 6: Atualiza o rastreamento da data de início do saldo negativo."""
        if Decimal(str(conta.saldo)) < Decimal("0.00"):
            if conta.data_saldo_negativo_inicio is None:
                conta.data_saldo_negativo_inicio = datetime.utcnow()
        else:
            conta.data_saldo_negativo_inicio = None

    @classmethod
    def depositar(cls, db: Session, req: DepositoRequest) -> Transacao:
        conta = db.query(Conta).filter(Conta.id == req.conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {req.conta_id} não encontrada.",
            )

        if conta.estado != EstadoConta.ATIVA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Não é permitido depósito em conta com estado '{conta.estado.value}'.",
            )

        # Atualiza o saldo da conta
        conta.saldo = Decimal(str(conta.saldo)) + Decimal(str(req.valor))
        cls._atualizar_data_saldo_negativo(conta)

        transacao = Transacao(
            conta_id=conta.id,
            tipo=TipoTransacao.DEPOSITO,
            valor=req.valor,
            data=datetime.utcnow(),
            estado=EstadoTransacao.EFETIVADA,
            descricao=req.descricao or "Depósito em conta corrente",
        )
        db.add(transacao)
        db.commit()
        db.refresh(transacao)
        return transacao

    @classmethod
    def sacar(cls, db: Session, req: SaqueRequest) -> Transacao:
        conta = db.query(Conta).filter(Conta.id == req.conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {req.conta_id} não encontrada.",
            )

        # Regra 1: Saque só em conta ativa, de cliente ativo
        if conta.estado != EstadoConta.ATIVA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Operação não permitida: a conta está com estado '{conta.estado.value}'.",
            )

        if conta.cliente.situacao != SituacaoCliente.ATIVO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Operação não permitida: o titular da conta está bloqueado.",
            )

        # Regra 1: Respeitar o limite diário acumulado de saque da categoria
        categoria = conta.cliente.categoria
        limite_diario = RegrasCategoriaService.get_limite_diario_saque(categoria)

        # Calcular o total já sacado hoje pela conta
        hoje_inicio = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        saques_hoje = db.query(func.coalesce(func.sum(Transacao.valor), Decimal("0.00"))).filter(
            Transacao.conta_id == conta.id,
            Transacao.tipo == TipoTransacao.SAQUE,
            Transacao.estado == EstadoTransacao.EFETIVADA,
            Transacao.data >= hoje_inicio,
        ).scalar() or Decimal("0.00")

        total_saques_com_atual = Decimal(str(saques_hoje)) + Decimal(str(req.valor))
        if total_saques_com_atual > limite_diario:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Limite diário de saque excedido para a categoria '{categoria.value}'. "
                    f"Limite diário: R$ {limite_diario:.2f}. "
                    f"Total já sacado hoje: R$ {saques_hoje:.2f}. "
                    f"Tentativa de saque: R$ {req.valor:.2f}."
                ),
            )

        # Regra 2: Verificar saldo disponível até o limite de crédito
        cls._verificar_saldo_disponivel(conta, Decimal(str(req.valor)))

        # Debitar valor da conta
        conta.saldo = Decimal(str(conta.saldo)) - Decimal(str(req.valor))
        cls._atualizar_data_saldo_negativo(conta)

        transacao = Transacao(
            conta_id=conta.id,
            tipo=TipoTransacao.SAQUE,
            valor=req.valor,
            data=datetime.utcnow(),
            estado=EstadoTransacao.EFETIVADA,
            descricao=req.descricao or "Saque em dinheiro",
        )
        db.add(transacao)
        db.commit()
        db.refresh(transacao)
        return transacao

    @classmethod
    def transferir(cls, db: Session, req: TransferenciaRequest) -> Transacao:
        if req.conta_origem_id == req.conta_destino_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A conta de origem e a conta de destino não podem ser as mesmas.",
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

        # Regra 1: Conta de origem ativa e cliente ativo
        if conta_origem.estado != EstadoConta.ATIVA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Conta de origem está com estado '{conta_origem.estado.value}'.",
            )

        if conta_origem.cliente.situacao != SituacaoCliente.ATIVO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Operação não permitida: o titular da conta de origem está bloqueado.",
            )

        # Conta de destino não pode estar encerrada
        if conta_destino.estado == EstadoConta.ENCERRADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A conta de destino está encerrada e não pode receber transferências.",
            )

        # Regra 1: Limite por transferência da categoria
        categoria = conta_origem.cliente.categoria
        limite_por_transf = RegrasCategoriaService.get_limite_por_transferencia(categoria)
        if Decimal(str(req.valor)) > limite_por_transf:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Valor excede o limite por transferência da categoria '{categoria.value}'. "
                    f"Limite máximo por operação: R$ {limite_por_transf:.2f}. "
                    f"Valor solicitado: R$ {req.valor:.2f}."
                ),
            )

        # Regra 3: Transferência entre contas do mesmo cliente é isenta de tarifa.
        # As demais consomem a franquia de transações isentas da categoria e, esgotada a franquia, geram tarifa.
        mesmo_cliente = (conta_origem.cliente_id == conta_destino.cliente_id)
        tarifa_valor = Decimal("0.00")
        tarifa_isenta = True

        if not mesmo_cliente:
            franquia_isenta = RegrasCategoriaService.get_transacoes_isentas_mes(categoria)
            if franquia_isenta is None:
                # Premium: transações isentas ilimitadas
                tarifa_valor = Decimal("0.00")
                tarifa_isenta = True
            else:
                # Contar transferências não isentas realizadas no mês corrente
                agora = datetime.utcnow()
                inicio_mes = datetime(agora.year, agora.month, 1)

                # Busca transferências realizadas no mês para contas de outros clientes
                transf_mes_count = db.query(Transacao).join(
                    Conta, Transacao.conta_destino_id == Conta.id
                ).filter(
                    Transacao.conta_id == conta_origem.id,
                    Transacao.tipo == TipoTransacao.TRANSFERENCIA,
                    Transacao.estado == EstadoTransacao.EFETIVADA,
                    Transacao.data >= inicio_mes,
                    Conta.cliente_id != conta_origem.cliente_id,
                ).count()

                if transf_mes_count < franquia_isenta:
                    tarifa_valor = Decimal("0.00")
                    tarifa_isenta = True
                else:
                    # Franquia esgotada: cobra tarifa
                    tarifa_valor = settings.TARIFA_TRANSFERENCIA_EXCEDENTE
                    tarifa_isenta = False

        # Regra 2: Verificar saldo disponível cobrindo transferência + tarifa (se houver)
        total_a_debitar = Decimal(str(req.valor)) + tarifa_valor
        cls._verificar_saldo_disponivel(conta_origem, total_a_debitar)

        # Executar débitos e créditos
        conta_origem.saldo = Decimal(str(conta_origem.saldo)) - total_a_debitar
        cls._atualizar_data_saldo_negativo(conta_origem)

        conta_destino.saldo = Decimal(str(conta_destino.saldo)) + Decimal(str(req.valor))
        cls._atualizar_data_saldo_negativo(conta_destino)

        # Registrar a transação de transferência
        transacao = Transacao(
            conta_id=conta_origem.id,
            conta_destino_id=conta_destino.id,
            tipo=TipoTransacao.TRANSFERENCIA,
            valor=req.valor,
            data=datetime.utcnow(),
            estado=EstadoTransacao.EFETIVADA,
            descricao=req.descricao or f"Transferência para conta {conta_destino.numero}",
        )
        db.add(transacao)

        # Registrar a tarifa correspondente
        tarifa = Tarifa(
            conta_id=conta_origem.id,
            tipo="transferencia" if tarifa_isenta else "transferencia_excedente",
            valor=tarifa_valor,
            data=datetime.utcnow(),
            estado=EstadoTarifa.ISENTA if tarifa_isenta else EstadoTarifa.COBRADA,
        )
        db.add(tarifa)

        db.commit()
        db.refresh(transacao)
        return transacao

    @classmethod
    def estornar(cls, db: Session, transacao_id: int) -> Transacao:
        """
        Regra 4: Uma transação efetivada pode ser estornada em até 24 horas.
        O estorno reverte o saldo das contas envolvidas e registra uma nova transação do tipo estorno.
        """
        transacao = db.query(Transacao).filter(Transacao.id == transacao_id).first()
        if not transacao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transação com ID {transacao_id} não encontrada.",
            )

        if transacao.estado != EstadoTransacao.EFETIVADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Apenas transações no estado 'efetivada' podem ser estornadas. Estado atual: '{transacao.estado.value}'.",
            )

        if transacao.tipo == TipoTransacao.ESTORNO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível estornar uma transação de estorno.",
            )

        # Verificação do prazo de até 24 horas
        tempo_decorrido = datetime.utcnow() - transacao.data
        if tempo_decorrido.total_seconds() > 24 * 3600:
            horas = tempo_decorrido.total_seconds() / 3600
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Prazo para estorno expirado. O estorno só é permitido em até 24 horas (decorridas {horas:.1f} horas).",
            )

        conta_origem = db.query(Conta).filter(Conta.id == transacao.conta_id).first()

        # Reversão de saldos
        if transacao.tipo == TipoTransacao.DEPOSITO:
            # Estorno de depósito: retira o dinheiro depositado da conta
            cls._verificar_saldo_disponivel(conta_origem, Decimal(str(transacao.valor)))
            conta_origem.saldo = Decimal(str(conta_origem.saldo)) - Decimal(str(transacao.valor))
            cls._atualizar_data_saldo_negativo(conta_origem)

        elif transacao.tipo == TipoTransacao.SAQUE:
            # Estorno de saque: devolve o dinheiro sacado para a conta
            conta_origem.saldo = Decimal(str(conta_origem.saldo)) + Decimal(str(transacao.valor))
            cls._atualizar_data_saldo_negativo(conta_origem)

        elif transacao.tipo == TipoTransacao.TRANSFERENCIA:
            # Estorno de transferência: debita da conta_destino e credita na conta_origem
            conta_destino = db.query(Conta).filter(Conta.id == transacao.conta_destino_id).first()
            if not conta_destino:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Conta de destino {transacao.conta_destino_id} não encontrada para estorno.",
                )

            # A conta de destino deve ter saldo+limite para devolver
            cls._verificar_saldo_disponivel(conta_destino, Decimal(str(transacao.valor)))

            conta_destino.saldo = Decimal(str(conta_destino.saldo)) - Decimal(str(transacao.valor))
            cls._atualizar_data_saldo_negativo(conta_destino)

            conta_origem.saldo = Decimal(str(conta_origem.saldo)) + Decimal(str(transacao.valor))
            cls._atualizar_data_saldo_negativo(conta_origem)

        # Atualizar estado da transação original para ESTORNADA
        transacao.estado = EstadoTransacao.ESTORNADA

        # Registrar nova transação do tipo ESTORNO
        estorno_transacao = Transacao(
            conta_id=transacao.conta_id,
            conta_destino_id=transacao.conta_destino_id,
            transacao_origem_id=transacao.id,
            tipo=TipoTransacao.ESTORNO,
            valor=transacao.valor,
            data=datetime.utcnow(),
            estado=EstadoTransacao.EFETIVADA,
            descricao=f"Estorno referente à transação #{transacao.id} ({transacao.tipo.value})",
        )
        db.add(estorno_transacao)

        db.commit()
        db.refresh(estorno_transacao)
        return estorno_transacao

    @classmethod
    def get_extrato(
        cls,
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
            or_(
                Transacao.conta_id == conta_id,
                Transacao.conta_destino_id == conta_id,
            )
        )

        if data_inicio:
            query = query.filter(Transacao.data >= data_inicio)
        if data_fim:
            query = query.filter(Transacao.data <= data_fim)

        transacoes = query.order_by(Transacao.data.desc()).all()

        saldo_disp = Decimal(str(conta.saldo)) + Decimal(str(conta.limite_de_credito))

        return ExtratoResponse(
            conta_id=conta.id,
            numero_conta=conta.numero,
            saldo_atual=conta.saldo,
            limite_de_credito=conta.limite_de_credito,
            saldo_disponivel=saldo_disp,
            total_transacoes=len(transacoes),
            transacoes=[TransacaoResponse.model_validate(t) for t in transacoes],
        )
