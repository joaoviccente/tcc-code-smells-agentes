from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import EstadoMulta
from app.schemas.multa import MultaResponse
from app.services import multa_service

router = APIRouter(prefix="/multas", tags=["Multas"])


@router.get("", response_model=List[MultaResponse], status_code=status.HTTP_200_OK)
def listar_multas(
    usuario_id: Optional[int] = None,
    estado: Optional[EstadoMulta] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return multa_service.get_multas(db, usuario_id=usuario_id, estado=estado, skip=skip, limit=limit)


@router.get("/usuario/{usuario_id}", response_model=List[MultaResponse], status_code=status.HTTP_200_OK)
def listar_multas_por_usuario(usuario_id: int, db: Session = Depends(get_db)):
    """Listar multas por usuário."""
    return multa_service.get_multas_por_usuario(db, usuario_id)


@router.get("/{id}", response_model=MultaResponse, status_code=status.HTTP_200_OK)
def obter_multa(id: int, db: Session = Depends(get_db)):
    return multa_service.get_multa_by_id(db, id)


@router.post("/{id}/pagar", response_model=MultaResponse, status_code=status.HTTP_200_OK)
def pagar_multa(id: int, db: Session = Depends(get_db)):
    """Registrar o pagamento de uma multa aberta."""
    return multa_service.pagar_multa(db, id)
