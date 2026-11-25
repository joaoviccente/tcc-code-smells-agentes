from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.tarifa import TarifaCreate, TarifaResponse
from app.services.tarifa_service import TarifaService

router = APIRouter(prefix="/tarifas", tags=["Tarifas"])


@router.post("", response_model=TarifaResponse, status_code=status.HTTP_201_CREATED)
def criar_tarifa(tarifa_in: TarifaCreate, db: Session = Depends(get_db)):
    return TarifaService.create(db, tarifa_in)


@router.get("/conta/{conta_id}", response_model=List[TarifaResponse])
def listar_tarifas_por_conta(
    conta_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    return TarifaService.list_by_conta(db, conta_id=conta_id, skip=skip, limit=limit)
