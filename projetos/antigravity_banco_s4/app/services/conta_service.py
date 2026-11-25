from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.conta import Conta
from app.models.cliente import Cliente
from app.models.cartao import Cartao
from app.models.fatura import Fatura
from app.models.enums import EstadoConta, EstadoCartao, EstadoFatura, SituacaoCliente
from app.schemas.conta import ContaCreate, ContaUpdate, ContaEncerramentoResponse


class ContaService:
    @staticmethod
    def create_conta(db: Session, conta_in: ContaCreate) -> Conta:
        # Verificar existência do cliente
        cliente = db.query(Cliente).filter(Cliente.id == conta_in.cliente_id).first()
        if not cliente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cliente com ID {conta_in.cliente_id} não encontrado.",
            )
        
        if cliente.situacao == SituacaoCliente.BLOQUEADO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível criar conta para um cliente bloqueado.",
            )

        # Verificar duplicidade de número de conta
        if db.query(Conta).filter(Conta.numero == conta_in.numero).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Conta com o número '{conta_in.numero}' já existe.",
            )

        db_conta = Conta(
            cliente_id=conta_in.cliente_id,
            numero=conta_in.numero,
            tipo=conta_in.tipo,
            saldo=conta_in.saldo_inicial,
            limite_de_credito=conta_in.limite_de_credito,
            estado=EstadoConta.ATIVA,
        )
        db.add(db_conta)
        db.commit()
        db.refresh(db_conta)
        return db_conta

    @staticmethod
    def get_conta(db: Session, conta_id: int) -> Conta:
        conta = db.query(Conta).filter(Conta.id == conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {conta_id} não encontrada.",
            )
        return conta

    @staticmethod
    def get_contas(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        cliente_id: Optional[int] = None,
        estado: Optional[EstadoConta] = None,
    ) -> List[Conta]:
        query = db.query(Conta)
        if cliente_id:
            query = query.filter(Conta.cliente_id == cliente_id)
        if estado:
            query = query.filter(Conta.estado == estado)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def update_conta(db: Session, conta_id: int, conta_in: ContaUpdate) -> Conta:
        conta = ContaService.get_conta(db, conta_id)
        
        if conta.estado == EstadoConta.ENCERRADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contas encerradas não podem ser alteradas.",
            )

        if conta_in.tipo is not None:
            conta.tipo = conta_in.tipo
        if conta_in.limite_de_credito is not None:
            conta.limite_de_credito = conta_in.limite_de_credito
        if conta_in.estado is not None:
            if conta_in.estado == EstadoConta.ENCERRADA:
                # Se solicitou encerramento via update, deve respeitar Regra 7
                ContaService.encerrar_conta(db, conta_id)
                db.refresh(conta)
                return conta
            conta.estado = conta_in.estado

        db.commit()
        db.refresh(conta)
        return conta

    @staticmethod
    def encerrar_conta(db: Session, conta_id: int) -> ContaEncerramentoResponse:
        """
        Regra 7: O encerramento de conta exige saldo zero e nenhuma fatura aberta.
        Ao encerrar, todos os cartões da conta são cancelados.
        """
        conta = ContaService.get_conta(db, conta_id)

        if conta.estado == EstadoConta.ENCERRADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta conta já se encontra encerrada.",
            )

        # Exigência 1: Saldo exatamente zero
        if Decimal(str(conta.saldo)) != Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Para encerrar a conta, o saldo deve ser exatamente zero. Saldo atual: R$ {conta.saldo:.2f}",
            )

        # Exigência 2: Nenhuma fatura aberta em nenhum cartão da conta
        cartoes = db.query(Cartao).filter(Cartao.conta_id == conta_id).all()
        cartoes_ids = [c.id for c in cartoes]

        if cartoes_ids:
            faturas_em_aberto = db.query(Fatura).filter(
                Fatura.cartao_id.in_(cartoes_ids),
                Fatura.estado != EstadoFatura.PAGA,
            ).all()

            # Checar se há saldo residual devedor
            faturas_pendentes = [
                f for f in faturas_em_aberto
                if (f.valor + f.juros_acumulados - f.valor_pago) > Decimal("0.00")
            ]

            if faturas_pendentes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"A conta possui {len(faturas_pendentes)} fatura(s) pendente(s) ou aberta(s) nos cartões vinculados. Quite-as antes do encerramento.",
                )

        # Executar encerramento da conta
        conta.estado = EstadoConta.ENCERRADA

        # Cancelar todos os cartões da conta
        cartoes_cancelados_ids = []
        for cartao in cartoes:
            cartao.estado = EstadoCartao.CANCELADO
            cartoes_cancelados_ids.append(cartao.id)

        db.commit()
        db.refresh(conta)

        return ContaEncerramentoResponse(
            mensagem="Conta encerrada com sucesso e cartões vinculados cancelados.",
            conta_id=conta.id,
            estado=conta.estado,
            cartoes_cancelados_ids=cartoes_cancelados_ids,
        )
