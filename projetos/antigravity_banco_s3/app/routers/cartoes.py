from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.cartao import CartaoCreate, CartaoUpdate, CartaoResponse
from app.schemas.fatura import FaturaCreate, FaturaResponse
from app.services.cartao_service import CartaoService
from app.services.fatura_service import FaturaService

router = APIRouter(prefix="/cartoes", tags=["Cartões"])


@router.post("", response_model=CartaoResponse, status_code=status.HTTP_201_CREATED)
def criar_cartao(cartao_in: CartaoCreate, db: Session = Depends(get_db)):
    return CartaoService.create(db, cartao_in)


@router.get("", response_model=List[CartaoResponse])
def listar_cartoes(
    conta_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return CartaoService.list(db, conta_id=conta_id, skip=skip, limit=limit)


@router.get("/{cartao_id}", response_model=CartaoResponse)
def obter_cartao(cartao_id: int, db: Session = Depends(get_db)):
    return CartaoService.get_by_id(db, cartao_id)


@router.put("/{cartao_id}", response_model=CartaoResponse)
def atualizar_cartao(
    cartao_id: int, cartao_in: CartaoUpdate, db: Session = Depends(get_db)
):
    return CartaoService.update(db, cartao_id, cartao_in)


@router.delete("/{cartao_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_cartao(cartao_id: int, db: Session = Depends(get_db)):
    CartaoService.delete(db, cartao_id)
    return None


@router.get("/{cartao_id}/faturas", response_model=List[FaturaResponse])
def listar_faturas_cartao(cartao_id: int, db: Session = Depends(get_db)):
    faturas = FaturaService.list_by_cartao(db, cartao_id)
    return [
        FaturaResponse(
            id=f.id,
            cartao_id=f.cartao_id,
            mes_referencia=f.mes_referencia,
            valor=f.valor,
            data_vencimento=f.data_vencimento,
            estado=f.estado,
            valor_pago=f.valor_pago,
            data_pagamento=f.data_pagamento,
            juros_acumulados=f.juros_acumulados,
            valor_total=f.valor + f.juros_acumulados,
        )
        for f in faturas
    ]


@router.post(
    "/{cartao_id}/faturas",
    response_model=FaturaResponse,
    status_code=status.HTTP_201_CREATED,
)
def criar_fatura(
    cartao_id: int, fatura_in: FaturaCreate, db: Session = Depends(get_db)
):
    fatura_in.cartao_id = cartao_id
    f = FaturaService.create(db, fatura_in)
    return FaturaResponse(
        id=f.id,
        cartao_id=f.cartao_id,
        mes_referencia=f.mes_referencia,
        valor=f.valor,
        data_vencimento=f.data_vencimento,
        estado=f.estado,
        valor_pago=f.valor_pago,
        data_pagamento=f.data_pagamento,
        juros_acumulados=f.juros_acumulados,
        valor_total=f.valor + f.juros_acumulados,
    )
