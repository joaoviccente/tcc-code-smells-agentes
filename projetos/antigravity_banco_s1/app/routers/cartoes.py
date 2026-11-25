from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cartao import EstadoCartao
from app.schemas.cartao import CartaoCreate, CartaoResponse, CartaoUpdate
from app.services.cartao_service import CartaoService

router = APIRouter(prefix="/cartoes", tags=["Cartões"])


@router.post("", response_model=CartaoResponse, status_code=status.HTTP_201_CREATED)
def criar_cartao(cartao_in: CartaoCreate, db: Session = Depends(get_db)):
    """Emite um novo cartão vinculado a uma conta."""
    return CartaoService.criar_cartao(db, cartao_in)


@router.get("", response_model=List[CartaoResponse], status_code=status.HTTP_200_OK)
def listar_cartoes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    conta_id: Optional[int] = None,
    estado: Optional[EstadoCartao] = None,
    db: Session = Depends(get_db),
):
    """Lista cartões com filtros opcionais por conta e estado."""
    return CartaoService.listar_cartoes(
        db,
        skip=skip,
        limit=limit,
        conta_id=conta_id,
        estado=estado.value if estado else None,
    )


@router.get("/{cartao_id}", response_model=CartaoResponse, status_code=status.HTTP_200_OK)
def obter_cartao(cartao_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de um cartão pelo ID."""
    return CartaoService.obter_cartao(db, cartao_id)


@router.put("/{cartao_id}", response_model=CartaoResponse, status_code=status.HTTP_200_OK)
def atualizar_cartao(
    cartao_id: int, cartao_in: CartaoUpdate, db: Session = Depends(get_db)
):
    """Atualiza limite ou estado de um cartão."""
    return CartaoService.atualizar_cartao(db, cartao_id, cartao_in)


@router.delete("/{cartao_id}", response_model=CartaoResponse, status_code=status.HTTP_200_OK)
def cancelar_cartao(cartao_id: int, db: Session = Depends(get_db)):
    """Cancela um cartão."""
    return CartaoService.cancelar_cartao(db, cartao_id)
