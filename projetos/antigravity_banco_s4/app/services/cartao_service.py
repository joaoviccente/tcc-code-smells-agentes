from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.cartao import Cartao
from app.models.conta import Conta
from app.models.enums import EstadoConta, EstadoCartao, SituacaoCliente
from app.schemas.cartao import CartaoCreate, CartaoUpdate


class CartaoService:
    @staticmethod
    def create_cartao(db: Session, cartao_in: CartaoCreate) -> Cartao:
        conta = db.query(Conta).filter(Conta.id == cartao_in.conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {cartao_in.conta_id} não encontrada.",
            )

        if conta.estado != EstadoConta.ATIVA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Não é possível emitir cartão para conta no estado '{conta.estado.value}'.",
            )

        if conta.cliente.situacao != SituacaoCliente.ATIVO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível emitir cartão para cliente bloqueado.",
            )

        if db.query(Cartao).filter(Cartao.numero == cartao_in.numero).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cartão com o número '{cartao_in.numero}' já existe.",
            )

        db_cartao = Cartao(
            conta_id=cartao_in.conta_id,
            numero=cartao_in.numero,
            limite=cartao_in.limite,
            estado=EstadoCartao.ATIVO,
        )
        db.add(db_cartao)
        db.commit()
        db.refresh(db_cartao)
        return db_cartao

    @staticmethod
    def get_cartao(db: Session, cartao_id: int) -> Cartao:
        cartao = db.query(Cartao).filter(Cartao.id == cartao_id).first()
        if not cartao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cartão com ID {cartao_id} não encontrado.",
            )
        return cartao

    @staticmethod
    def get_cartoes(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        conta_id: Optional[int] = None,
        estado: Optional[EstadoCartao] = None,
    ) -> List[Cartao]:
        query = db.query(Cartao)
        if conta_id:
            query = query.filter(Cartao.conta_id == conta_id)
        if estado:
            query = query.filter(Cartao.estado == estado)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def update_cartao(db: Session, cartao_id: int, cartao_in: CartaoUpdate) -> Cartao:
        cartao = CartaoService.get_cartao(db, cartao_id)

        if cartao.estado == EstadoCartao.CANCELADO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cartão cancelado não pode ser alterado.",
            )

        if cartao_in.limite is not None:
            cartao.limite = cartao_in.limite
        if cartao_in.estado is not None:
            cartao.estado = cartao_in.estado

        db.commit()
        db.refresh(cartao)
        return cartao

    @staticmethod
    def cancelar_cartao(db: Session, cartao_id: int) -> Cartao:
        cartao = CartaoService.get_cartao(db, cartao_id)
        cartao.estado = EstadoCartao.CANCELADO
        db.commit()
        db.refresh(cartao)
        return cartao
