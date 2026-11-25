from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import EstadoMulta
from app.schemas.multa import MultaPagamentoResponse, MultaResponse
from app.services import multa_service

router = APIRouter(prefix="/multas", tags=["Multas"])


@router.get("/usuario/{usuario_id}", response_model=List[MultaResponse])
def listar_multas_por_usuario(
    usuario_id: int,
    estado: Optional[EstadoMulta] = None,
    db: Session = Depends(get_db),
):
    return multa_service.list_multas_usuario(db, usuario_id, estado=estado)


@router.post("/{multa_id}/pagar", response_model=MultaPagamentoResponse)
def registrar_pagamento_multa(
    multa_id: int,
    data_pagamento: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    multa = multa_service.registrar_pagamento(
        db, multa_id, data_pagamento=data_pagamento
    )
    return MultaPagamentoResponse(
        mensagem="Pagamento registrado com sucesso.",
        multa=MultaResponse.model_validate(multa),
    )


@router.get("", response_model=List[MultaResponse])
def listar_todas_multas(
    estado: Optional[EstadoMulta] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return multa_service.list_multas(db, estado=estado, skip=skip, limit=limit)


@router.get("/{multa_id}", response_model=MultaResponse)
def obter_multa(multa_id: int, db: Session = Depends(get_db)):
    return multa_service.get_multa(db, multa_id)
