from typing import Optional, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import EstadoCartao, EstadoFatura
from app.schemas.cartao import CartaoCreate, CartaoUpdate, CartaoResponse
from app.schemas.fatura import FaturaResponse
from app.services import cartao_service, fatura_service

router = APIRouter(prefix="/cartoes", tags=["Cartões"])


@router.post("", response_model=CartaoResponse, status_code=status.HTTP_201_CREATED)
def criar_cartao(cartao_in: CartaoCreate, db: Session = Depends(get_db)):
    return cartao_service.criar_cartao(db, cartao_in)


@router.get("", response_model=List[CartaoResponse], status_code=status.HTTP_200_OK)
def listar_cartoes(
    conta_id: Optional[int] = None,
    estado: Optional[EstadoCartao] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return cartao_service.listar_cartoes(db, conta_id, estado, skip, limit)


@router.get("/{cartao_id}", response_model=CartaoResponse, status_code=status.HTTP_200_OK)
def obter_cartao(cartao_id: int, db: Session = Depends(get_db)):
    return cartao_service.obter_cartao_por_id(db, cartao_id)


@router.put("/{cartao_id}", response_model=CartaoResponse, status_code=status.HTTP_200_OK)
def atualizar_cartao(
    cartao_id: int,
    cartao_in: CartaoUpdate,
    db: Session = Depends(get_db),
):
    return cartao_service.atualizar_cartao(db, cartao_id, cartao_in)


@router.delete("/{cartao_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_cartao(cartao_id: int, db: Session = Depends(get_db)):
    cartao_service.deletar_cartao(db, cartao_id)
    return None


@router.get("/{cartao_id}/faturas", response_model=List[FaturaResponse], status_code=status.HTTP_200_OK)
def listar_faturas_do_cartao(
    cartao_id: int,
    estado: Optional[EstadoFatura] = None,
    db: Session = Depends(get_db),
):
    return fatura_service.listar_faturas_por_cartao(db, cartao_id, estado)
