from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.fatura import FaturaCreate, FaturaPagamentoRequest, FaturaResponse
from app.services import fatura_service

router = APIRouter(prefix="/faturas", tags=["Faturas"])


@router.post("", response_model=FaturaResponse, status_code=status.HTTP_201_CREATED)
def criar_fatura(fatura_in: FaturaCreate, db: Session = Depends(get_db)):
    """Gera uma nova fatura para um cartão."""
    fatura = fatura_service.criar_fatura(db, fatura_in)
    return fatura_service.fatura_to_response(fatura)


@router.get("/{fatura_id}", response_model=FaturaResponse, status_code=status.HTTP_200_OK)
def obter_fatura(fatura_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes da fatura com cálculo atualizado de juros se vencida."""
    fatura = fatura_service.obter_fatura_por_id(db, fatura_id)
    return fatura_service.fatura_to_response(fatura)


@router.post("/{fatura_id}/pagamento", response_model=FaturaResponse, status_code=status.HTTP_200_OK)
def pagar_fatura(fatura_id: int, req: FaturaPagamentoRequest, db: Session = Depends(get_db)):
    """
    Registra o pagamento de uma fatura.
    Opcionalmente debita de uma conta corrente/poupança se informada.
    Se o cartão estava bloqueado por atraso superior a 10 dias, restaura o cartão caso não haja outras faturas em atraso crítico.
    """
    fatura = fatura_service.registrar_pagamento_fatura(db, fatura_id, req)
    return fatura_service.fatura_to_response(fatura)
