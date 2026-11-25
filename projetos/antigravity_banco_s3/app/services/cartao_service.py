from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.cartao import Cartao
from app.models.conta import Conta
from app.schemas.cartao import CartaoCreate, CartaoUpdate
from app.config import EstadoConta, EstadoCartao


class CartaoService:
    @staticmethod
    def get_by_id(db: Session, cartao_id: int) -> Cartao:
        cartao = db.query(Cartao).filter(Cartao.id == cartao_id).first()
        if not cartao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cartão com ID {cartao_id} não encontrado.",
            )
        return cartao

    @staticmethod
    def get_by_numero(db: Session, numero: str) -> Optional[Cartao]:
        return db.query(Cartao).filter(Cartao.numero == numero).first()

    @staticmethod
    def list(
        db: Session,
        conta_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Cartao]:
        query = db.query(Cartao)
        if conta_id:
            query = query.filter(Cartao.conta_id == conta_id)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def create(db: Session, cartao_in: CartaoCreate) -> Cartao:
        conta = db.query(Conta).filter(Conta.id == cartao_in.conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {cartao_in.conta_id} não encontrada.",
            )

        if conta.estado != EstadoConta.ATIVA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Não é possível emitir cartão para conta em estado '{conta.estado.value}'.",
            )

        if CartaoService.get_by_numero(db, cartao_in.numero):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cartão com número {cartao_in.numero} já existente.",
            )

        cartao = Cartao(
            conta_id=cartao_in.conta_id,
            numero=cartao_in.numero,
            limite=cartao_in.limite,
            estado=EstadoCartao.ATIVO,
        )
        db.add(cartao)
        db.commit()
        db.refresh(cartao)
        return cartao

    @staticmethod
    def update(db: Session, cartao_id: int, cartao_in: CartaoUpdate) -> Cartao:
        cartao = CartaoService.get_by_id(db, cartao_id)

        if cartao_in.limite is not None:
            cartao.limite = cartao_in.limite
        if cartao_in.estado is not None:
            cartao.estado = cartao_in.estado

        db.commit()
        db.refresh(cartao)
        return cartao

    @staticmethod
    def delete(db: Session, cartao_id: int) -> None:
        cartao = CartaoService.get_by_id(db, cartao_id)
        db.delete(cartao)
        db.commit()
