from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.cartao import Cartao
from app.models.conta import Conta
from app.schemas.cartao import CartaoCreate, CartaoUpdate
from app.config import EstadoCartao, EstadoConta


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

    if db.query(Cartao).filter(Cartao.numero == cartao_in.numero).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe um cartão com o número {cartao_in.numero}.",
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


def listar_cartoes(
    db: Session,
    conta_id: Optional[int] = None,
    estado: Optional[EstadoCartao] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Cartao]:
    query = db.query(Cartao)
    if conta_id:
        query = query.filter(Cartao.conta_id == conta_id)
    if estado:
        query = query.filter(Cartao.estado == estado)
    return query.offset(skip).limit(limit).all()


def obter_cartao_por_id(db: Session, cartao_id: int) -> Cartao:
    cartao = db.query(Cartao).filter(Cartao.id == cartao_id).first()
    if not cartao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cartão #{cartao_id} não encontrado.",
        )
    return cartao


def atualizar_cartao(db: Session, cartao_id: int, cartao_in: CartaoUpdate) -> Cartao:
    cartao = obter_cartao_por_id(db, cartao_id)

    if cartao_in.limite is not None:
        cartao.limite = cartao_in.limite
    if cartao_in.estado is not None:
        cartao.estado = cartao_in.estado

    db.commit()
    db.refresh(cartao)
    return cartao


def cancelar_cartao(db: Session, cartao_id: int) -> Cartao:
    cartao = obter_cartao_por_id(db, cartao_id)
    cartao.estado = EstadoCartao.CANCELADO
    db.commit()
    db.refresh(cartao)
    return cartao
