from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.fatura import FaturaCreate, FaturaPagamentoRequest, FaturaResponse
from app.services.fatura_service import FaturaService

router = APIRouter(tags=["Faturas"])


@router.get("/cartoes/{cartao_id}/faturas", response_model=List[FaturaResponse])
def listar_faturas_por_cartao(cartao_id: int, db: Session = Depends(get_db)):
    """Lista todas as faturas de um cartão, atualizando automaticamente juros e status se vencidas."""
    faturas = FaturaService.listar_por_cartao(db, cartao_id)
    return [FaturaService.to_response(f) for f in faturas]


@router.post("/cartoes/{cartao_id}/faturas", response_model=FaturaResponse, status_code=status.HTTP_201_CREATED)
def criar_fatura_para_cartao(cartao_id: int, req: FaturaCreate, db: Session = Depends(get_db)):
    """Gera uma fatura para o cartão indicado."""
    if req.cartao_id != cartao_id:
        req.cartao_id = cartao_id
    fatura = FaturaService.criar_fatura(db, req)
    return FaturaService.to_response(fatura)


@router.post("/faturas", response_model=FaturaResponse, status_code=status.HTTP_201_CREATED)
def criar_fatura_geral(req: FaturaCreate, db: Session = Depends(get_db)):
    """Gera uma fatura para o cartão especificado no corpo da requisição."""
    fatura = FaturaService.criar_fatura(db, req)
    return FaturaService.to_response(fatura)


@router.get("/faturas/{fatura_id}", response_model=FaturaResponse)
def obter_fatura(fatura_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma fatura, atualizando eventuais juros se vencida."""
    fatura = FaturaService.get_fatura(db, fatura_id)
    return FaturaService.to_response(fatura)


@router.post("/faturas/{fatura_id}/pagamento", response_model=FaturaResponse)
def registrar_pagamento_fatura(fatura_id: int, req: FaturaPagamentoRequest, db: Session = Depends(get_db)):
    """Registra pagamento (parcial ou integral) de uma fatura."""
    fatura = FaturaService.registrar_pagamento(db, fatura_id, req)
    return FaturaService.to_response(fatura)
