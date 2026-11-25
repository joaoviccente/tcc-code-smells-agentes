from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.cartao import Cartao
from app.models.conta import Conta
from app.models.fatura import Fatura
from app.schemas.cartao import CartaoCreate, CartaoUpdate
from app.config import EstadoConta, EstadoCartao, EstadoFatura


def criar_cartao(db: Session, cartao_in: CartaoCreate) -> Cartao:
    conta = db.query(Conta).filter(Conta.id == cartao_in.conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta com ID {cartao_in.conta_id} não encontrada."
        )

    if conta.estado != EstadoConta.ATIVA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não é possível emitir cartão para conta no estado '{conta.estado.value}'."
        )

    # Verifica unicidade do número do cartão
    if db.query(Cartao).filter(Cartao.numero == cartao_in.numero).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe um cartão com o número {cartao_in.numero}."
        )

    db_cartao = Cartao(
        conta_id=cartao_in.conta_id,
        numero=cartao_in.numero,
        limite=cartao_in.limite,
        estado=cartao_in.estado,
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
            detail=f"Cartão com ID {cartao_id} não encontrado."
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


def deletar_cartao(db: Session, cartao_id: int) -> None:
    cartao = obter_cartao_por_id(db, cartao_id)
    faturas_pendentes = db.query(Fatura).filter(
        Fatura.cartao_id == cartao.id,
        Fatura.estado.in_([EstadoFatura.ABERTA, EstadoFatura.ATRASADA])
    ).first()
    if faturas_pendentes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir cartão com faturas abertas ou atrasadas."
        )
    db.delete(cartao)
    db.commit()
