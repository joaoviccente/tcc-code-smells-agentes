from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import EstadoMulta
from app.schemas.multa import MultaResponse
from app.services import multa_service

router = APIRouter(prefix="/multas", tags=["Multas"])


@router.get("/usuario/{usuario_id}", response_model=List[MultaResponse])
def listar_multas_por_usuario(usuario_id: int, db: Session = Depends(get_db)):
    """
    Lista todas as multas geradas para um usuário.
    """
    return multa_service.get_multas_por_usuario(db, usuario_id)


@router.post("/{id}/pagar", response_model=MultaResponse)
def registrar_pagamento(id: int, db: Session = Depends(get_db)):
    """
    Registra o pagamento de uma multa aberta.
    """
    return multa_service.registrar_pagamento_multa(db, id)


@router.get("", response_model=List[MultaResponse])
def listar_todas_multas(
    estado: Optional[EstadoMulta] = Query(None, description="Filtrar por estado: aberta, paga, perdoada"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lista multas cadastradas."""
    return multa_service.get_multas(db, estado=estado, skip=skip, limit=limit)


@router.get("/{id}", response_model=MultaResponse)
def obter_multa(id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma multa específica."""
    return multa_service.get_multa_by_id(db, id)
