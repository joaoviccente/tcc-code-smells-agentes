from typing import Optional, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tarifa import Tarifa
from app.config import EstadoTarifa
from app.schemas.tarifa import (
    TarifaCreate,
    TarifaResponse,
    CobrancaMensalResponse,
)
from app.services import tarifa_service

router = APIRouter(prefix="/tarifas", tags=["Tarifas"])


@router.post("", response_model=TarifaResponse, status_code=status.HTTP_201_CREATED)
def criar_tarifa(tarifa_in: TarifaCreate, db: Session = Depends(get_db)):
    return tarifa_service.criar_tarifa(db, tarifa_in)


@router.get("", response_model=List[TarifaResponse], status_code=status.HTTP_200_OK)
def listar_tarifas(
    conta_id: Optional[int] = None,
    estado: Optional[EstadoTarifa] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Tarifa)
    if conta_id:
        query = query.filter(Tarifa.conta_id == conta_id)
    if estado:
        query = query.filter(Tarifa.estado == estado)
    return query.order_by(Tarifa.data.desc()).all()


@router.post("/cobranca-mensal", response_model=CobrancaMensalResponse, status_code=status.HTTP_200_OK)
def processar_cobranca_mensal(db: Session = Depends(get_db)):
    return tarifa_service.processar_cobranca_mensal(db)
