from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.tarifa import Tarifa
from app.schemas.tarifa import TarifaResponse
from app.config import EstadoTarifa, TipoTarifa
from app.services import tarifa_service

router = APIRouter(prefix="/tarifas", tags=["Tarifas"])


@router.get("", response_model=List[TarifaResponse], status_code=status.HTTP_200_OK)
def listar_todas_tarifas(
    conta_id: Optional[int] = Query(None, description="Filtrar por ID da conta"),
    tipo: Optional[TipoTarifa] = Query(None, description="Filtrar por tipo de tarifa"),
    estado: Optional[EstadoTarifa] = Query(None, description="Filtrar por estado"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Lista tarifas com filtros opcionais por conta, tipo ou estado."""
    query = db.query(Tarifa)
    if conta_id:
        query = query.filter(Tarifa.conta_id == conta_id)
    if tipo:
        query = query.filter(Tarifa.tipo == tipo)
    if estado:
        query = query.filter(Tarifa.estado == estado)
    return query.offset(skip).limit(limit).all()


@router.get("/conta/{conta_id}", response_model=List[TarifaResponse], status_code=status.HTTP_200_OK)
def listar_tarifas_por_conta(conta_id: int, db: Session = Depends(get_db)):
    """Lista todas as tarifas de uma conta específica."""
    return tarifa_service.listar_tarifas_por_conta(db, conta_id)
