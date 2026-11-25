from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import EstadoMulta
from app.schemas import MultaResponse
import app.services as services

router = APIRouter(prefix="/multas", tags=["Multas"])

@router.get("", response_model=List[MultaResponse], status_code=status.HTTP_200_OK)
def listar_multas(
    usuario_id: Optional[int] = None,
    estado: Optional[EstadoMulta] = None,
    db: Session = Depends(get_db)
):
    return services.get_multas(db, usuario_id=usuario_id, estado=estado)

@router.get("/{multa_id}", response_model=MultaResponse, status_code=status.HTTP_200_OK)
def buscar_multa(multa_id: int, db: Session = Depends(get_db)):
    return services.get_multa(db, multa_id)

@router.post("/{multa_id}/pagar", response_model=MultaResponse, status_code=status.HTTP_200_OK)
def pagar_multa(multa_id: int, db: Session = Depends(get_db)):
    return services.pagar_multa(db, multa_id)

@router.put("/{multa_id}/pagar", response_model=MultaResponse, status_code=status.HTTP_200_OK)
def pagar_multa_put(multa_id: int, db: Session = Depends(get_db)):
    return services.pagar_multa(db, multa_id)
