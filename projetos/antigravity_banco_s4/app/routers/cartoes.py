from typing import List, Optional
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import EstadoCartao
from app.schemas.cartao import CartaoCreate, CartaoUpdate, CartaoResponse
from app.services.cartao_service import CartaoService

router = APIRouter(prefix="/cartoes", tags=["Cartões"])


@router.post("", response_model=CartaoResponse, status_code=status.HTTP_201_CREATED)
def criar_cartao(cartao_in: CartaoCreate, db: Session = Depends(get_db)):
    """Emite um novo cartão para uma conta ativa."""
    return CartaoService.create_cartao(db, cartao_in)


@router.get("", response_model=List[CartaoResponse])
def listar_cartoes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    conta_id: Optional[int] = None,
    estado: Optional[EstadoCartao] = None,
    db: Session = Depends(get_db),
):
    """Lista cartões com filtros opcionais por conta e estado."""
    return CartaoService.get_cartoes(db, skip=skip, limit=limit, conta_id=conta_id, estado=estado)


@router.get("/{cartao_id}", response_model=CartaoResponse)
def obter_cartao(cartao_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de um cartão específico."""
    return CartaoService.get_cartao(db, cartao_id)


@router.put("/{cartao_id}", response_model=CartaoResponse)
def atualizar_cartao(cartao_id: int, cartao_in: CartaoUpdate, db: Session = Depends(get_db)):
    """Atualiza limite ou estado de um cartão."""
    return CartaoService.update_cartao(db, cartao_id, cartao_in)


@router.delete("/{cartao_id}", response_model=CartaoResponse)
def cancelar_cartao(cartao_id: int, db: Session = Depends(get_db)):
    """Cancela um cartão."""
    return CartaoService.cancelar_cartao(db, cartao_id)
