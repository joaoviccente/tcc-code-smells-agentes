from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.fatura import (
    FaturaCreate,
    FaturaPagamentoCreate,
    FaturaResponse,
    ProcessarAtrasosResponse,
)
from app.services import fatura_service

router = APIRouter(prefix="/faturas", tags=["Faturas"])


@router.post("", response_model=FaturaResponse, status_code=status.HTTP_201_CREATED)
def criar_fatura(fatura_in: FaturaCreate, db: Session = Depends(get_db)):
    return fatura_service.criar_fatura(db, fatura_in)


@router.get("/{fatura_id}", response_model=FaturaResponse, status_code=status.HTTP_200_OK)
def obter_fatura(fatura_id: int, db: Session = Depends(get_db)):
    return fatura_service.obter_fatura_por_id(db, fatura_id)


@router.post("/{fatura_id}/pagamento", response_model=FaturaResponse, status_code=status.HTTP_200_OK)
def registrar_pagamento(
    fatura_id: int,
    pagamento_in: FaturaPagamentoCreate,
    db: Session = Depends(get_db),
):
    return fatura_service.registrar_pagamento_fatura(db, fatura_id, pagamento_in)


@router.post("/processar-atrasos", response_model=ProcessarAtrasosResponse, status_code=status.HTTP_200_OK)
def processar_atrasos(
    data_ref: Optional[date] = None,
    db: Session = Depends(get_db),
):
    return fatura_service.processar_atrasos(db, data_ref)
