from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.conta import Conta
from app.models.cliente import Cliente
from app.models.cartao import Cartao
from app.models.fatura import Fatura
from app.models.transacao import Transacao
from app.schemas.conta import ContaCreate, ContaUpdate
from app.config import EstadoConta, EstadoCartao, EstadoFatura, TipoTransacao, EstadoTransacao


class ContaService:
    @staticmethod
    def get_by_id(db: Session, conta_id: int) -> Conta:
        conta = db.query(Conta).filter(Conta.id == conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {conta_id} não encontrada.",
            )
        return conta

    @staticmethod
    def get_by_numero(db: Session, numero: str) -> Optional[Conta]:
        return db.query(Conta).filter(Conta.numero == numero).first()

    @staticmethod
    def list(
        db: Session,
        cliente_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Conta]:
        query = db.query(Conta)
        if cliente_id:
            query = query.filter(Conta.cliente_id == cliente_id)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def create(db: Session, conta_in: ContaCreate) -> Conta:
        # Verifica cliente
        cliente = db.query(Cliente).filter(Cliente.id == conta_in.cliente_id).first()
        if not cliente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cliente com ID {conta_in.cliente_id} não encontrado.",
            )

        # Verifica número duplicado
        if ContaService.get_by_numero(db, conta_in.numero):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Número de conta {conta_in.numero} já existente.",
            )

        if conta_in.saldo_inicial < 0 and abs(conta_in.saldo_inicial) > conta_in.limite_credito:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Saldo inicial negativo não pode exceder o limite de crédito.",
            )

        saldo_negativo_desde = (
            datetime.now(timezone.utc) if conta_in.saldo_inicial < 0 else None
        )

        conta = Conta(
            cliente_id=conta_in.cliente_id,
            numero=conta_in.numero,
            tipo=conta_in.tipo,
            saldo=conta_in.saldo_inicial,
            limite_credito=conta_in.limite_credito,
            estado=EstadoConta.ATIVA,
            saldo_negativo_desde=saldo_negativo_desde,
        )
        db.add(conta)
        db.commit()
        db.refresh(conta)

        if conta_in.saldo_inicial > 0:
            transacao = Transacao(
                conta_id=conta.id,
                tipo=TipoTransacao.DEPOSITO,
                valor=conta_in.saldo_inicial,
                estado=EstadoTransacao.EFETIVADA,
                descricao="Depósito inicial de abertura de conta",
            )
            db.add(transacao)
            db.commit()

        return conta

    @staticmethod
    def update(db: Session, conta_id: int, conta_in: ContaUpdate) -> Conta:
        conta = ContaService.get_by_id(db, conta_id)

        if conta_in.tipo is not None:
            conta.tipo = conta_in.tipo
        if conta_in.limite_credito is not None:
            # Não permitir reduzir limite abaixo da dívida atual se saldo for negativo
            if conta.saldo < 0 and abs(conta.saldo) > conta_in.limite_credito:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"O novo limite de crédito (R$ {conta_in.limite_credito}) não pode ser inferior ao saldo devedor atual (R$ {abs(conta.saldo)}).",
                )
            conta.limite_credito = conta_in.limite_credito
        if conta_in.estado is not None:
            conta.estado = conta_in.estado

        db.commit()
        db.refresh(conta)
        return conta

    @staticmethod
    def encerrar(db: Session, conta_id: int) -> Conta:
        """
        Regra 7: O encerramento de conta exige saldo zero e nenhuma fatura aberta.
        Ao encerrar, todos os cartões da conta são cancelados.
        """
        conta = ContaService.get_by_id(db, conta_id)

        if conta.estado == EstadoConta.ENCERRADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A conta já se encontra encerrada.",
            )

        if conta.saldo != Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"O encerramento de conta exige saldo zero. Saldo atual: R$ {conta.saldo:.2f}.",
            )

        # Verifica faturas abertas ou atrasadas nos cartões vinculados à conta
        cartoes = db.query(Cartao).filter(Cartao.conta_id == conta_id).all()
        for cartao in cartoes:
            faturas_pendentes = (
                db.query(Fatura)
                .filter(
                    Fatura.cartao_id == cartao.id,
                    Fatura.estado.in_([EstadoFatura.ABERTA, EstadoFatura.ATRASADA]),
                )
                .count()
            )
            if faturas_pendentes > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Não é possível encerrar a conta: existem faturas abertas ou em atraso vinculadas aos seus cartões.",
                )

        # Encerra conta
        conta.estado = EstadoConta.ENCERRADA

        # Cancela todos os cartões da conta
        for cartao in cartoes:
            cartao.estado = EstadoCartao.CANCELADO

        db.commit()
        db.refresh(conta)
        return conta

    @staticmethod
    def delete(db: Session, conta_id: int) -> None:
        conta = ContaService.get_by_id(db, conta_id)
        if conta.saldo != Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível excluir conta com saldo diferente de zero.",
            )
        db.delete(conta)
        db.commit()
