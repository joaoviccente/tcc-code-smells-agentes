from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.config import EstadoMulta
from app.database import get_db
from app.schemas.multa import MultaResponse, PagamentoMultaResponse
from app.services import multa_service

router = APIRouter(prefix="/multas", tags=["Multas"])


@router.get("/usuario/{usuario_id}", response_model=list[MultaResponse])
def listar_multas_por_usuario(usuario_id: int, db: Session = Depends(get_db)):
    return multa_service.listar_multas_por_usuario(db, usuario_id)


@router.post("/{multa_id}/pagar", response_model=PagamentoMultaResponse)
def registrar_pagamento_multa(multa_id: int, db: Session = Depends(get_db)):
    multa_paga = multa_service.registrar_pagamento_multa(db, multa_id)
    return PagamentoMultaResponse(
        mensagem="Pagamento de multa registrado com sucesso.",
        multa=multa_paga,
    )


@router.get("", response_model=list[MultaResponse])
def listar_todas_multas(
    estado: EstadoMulta | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return multa_service.listar_todas_multas(db, estado=estado, skip=skip, limit=limit)
