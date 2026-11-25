from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.cartao import CartaoCreate, CartaoUpdate, CartaoResponse
from app.schemas.fatura import FaturaResponse
from app.config import EstadoCartao
from app.services import cartao_service, fatura_service

router = APIRouter(prefix="/cartoes", tags=["Cartões"])


@router.post("", response_model=CartaoResponse, status_code=status.HTTP_201_CREATED)
def criar_cartao(cartao_in: CartaoCreate, db: Session = Depends(get_db)):
    """Emite um novo cartão vinculado a uma conta."""
    return cartao_service.criar_cartao(db, cartao_in)


@router.get("", response_model=List[CartaoResponse], status_code=status.HTTP_200_OK)
def listar_cartoes(
    conta_id: Optional[int] = Query(None, description="Filtrar por conta"),
    estado: Optional[EstadoCartao] = Query(None, description="Filtrar por estado"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Lista cartões com filtros e paginação."""
    return cartao_service.listar_cartoes(db, conta_id=conta_id, estado=estado, skip=skip, limit=limit)


@router.get("/{cartao_id}", response_model=CartaoResponse, status_code=status.HTTP_200_OK)
def obter_cartao(cartao_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de um cartão específico."""
    return cartao_service.obter_cartao_por_id(db, cartao_id)


@router.put("/{cartao_id}", response_model=CartaoResponse, status_code=status.HTTP_200_OK)
def atualizar_cartao(cartao_id: int, cartao_in: CartaoUpdate, db: Session = Depends(get_db)):
    """Atualiza limite ou estado de um cartão."""
    return cartao_service.atualizar_cartao(db, cartao_id, cartao_in)


@router.delete("/{cartao_id}", response_model=CartaoResponse, status_code=status.HTTP_200_OK)
def cancelar_cartao(cartao_id: int, db: Session = Depends(get_db)):
    """Cancela um cartão."""
    return cartao_service.cancelar_cartao(db, cartao_id)


@router.get("/{cartao_id}/faturas", response_model=List[FaturaResponse], status_code=status.HTTP_200_OK)
def listar_faturas_do_cartao(cartao_id: int, db: Session = Depends(get_db)):
    """Lista todas as faturas associadas a um cartão, atualizando juros e status se vencidas."""
    faturas = fatura_service.listar_faturas_por_cartao(db, cartao_id)
    return [fatura_service.fatura_to_response(f) for f in faturas]
