from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.cartao import Cartao, EstadoCartao
from app.models.conta import Conta, EstadoConta
from app.schemas.cartao import CartaoCreate, CartaoUpdate


class CartaoService:
    @staticmethod
    def criar_cartao(db: Session, cartao_in: CartaoCreate) -> Cartao:
        conta = db.query(Conta).filter(Conta.id == cartao_in.conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta #{cartao_in.conta_id} não encontrada.",
            )

        if conta.estado == EstadoConta.ENCERRADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível emitir cartão para uma conta encerrada.",
            )

        # Verifica duplicidade de número de cartão
        if db.query(Cartao).filter(Cartao.numero == cartao_in.numero).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Já existe um cartão cadastrado com o número {cartao_in.numero}.",
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
    def obter_cartao(db: Session, cartao_id: int) -> Cartao:
        cartao = db.query(Cartao).filter(Cartao.id == cartao_id).first()
        if not cartao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cartão #{cartao_id} não encontrado.",
            )
        return cartao

    @staticmethod
    def listar_cartoes(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        conta_id: Optional[int] = None,
        estado: Optional[str] = None,
    ) -> List[Cartao]:
        query = db.query(Cartao)
        if conta_id is not None:
            query = query.filter(Cartao.conta_id == conta_id)
        if estado is not None:
            query = query.filter(Cartao.estado == estado)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def atualizar_cartao(db: Session, cartao_id: int, cartao_in: CartaoUpdate) -> Cartao:
        cartao = CartaoService.obter_cartao(db, cartao_id)

        if cartao_in.limite is not None:
            cartao.limite = cartao_in.limite
        if cartao_in.estado is not None:
            cartao.estado = cartao_in.estado

        db.commit()
        db.refresh(cartao)
        return cartao

    @staticmethod
    def cancelar_cartao(db: Session, cartao_id: int) -> Cartao:
        cartao = CartaoService.obter_cartao(db, cartao_id)
        cartao.estado = EstadoCartao.CANCELADO
        db.commit()
        db.refresh(cartao)
        return cartao
