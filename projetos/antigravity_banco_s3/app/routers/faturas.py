from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.fatura import FaturaCreate, FaturaPagamentoRequest, FaturaResponse
from app.services.fatura_service import FaturaService

router = APIRouter(prefix="/faturas", tags=["Faturas"])


@router.post("", response_model=FaturaResponse, status_code=status.HTTP_201_CREATED)
def criar_fatura(fatura_in: FaturaCreate, db: Session = Depends(get_db)):
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


@router.get("/{fatura_id}", response_model=FaturaResponse)
def obter_fatura(fatura_id: int, db: Session = Depends(get_db)):
    f = FaturaService.get_by_id(db, fatura_id)
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


@router.post("/{fatura_id}/pagamento", response_model=FaturaResponse)
def registrar_pagamento_fatura(
    fatura_id: int, req: FaturaPagamentoRequest, db: Session = Depends(get_db)
):
    f = FaturaService.registrar_pagamento(db, fatura_id, req)
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
