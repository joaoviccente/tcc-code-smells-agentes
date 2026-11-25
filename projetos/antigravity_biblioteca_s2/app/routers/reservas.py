from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import EstadoReserva
from app.schemas.reserva import ReservaCreate, ReservaResponse
from app.services import reserva_service

router = APIRouter(prefix="/reservas", tags=["Reservas"])


@router.post("", response_model=ReservaResponse, status_code=status.HTTP_201_CREATED)
def criar_reserva(reserva_in: ReservaCreate, db: Session = Depends(get_db)):
    return reserva_service.create_reserva(db, reserva_in)


@router.post("/{reserva_id}/cancelar", response_model=ReservaResponse)
def cancelar_reserva(
    reserva_id: int,
    data_referencia: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    return reserva_service.cancel_reserva(
        db, reserva_id, data_referencia=data_referencia
    )


@router.get("/livro/{livro_id}", response_model=List[ReservaResponse])
def listar_fila_do_livro(
    livro_id: int,
    data_referencia: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return reserva_service.list_fila_livro(
        db, livro_id, data_referencia=data_referencia
    )


@router.post("/processar-expiracoes", response_model=List[ReservaResponse])
def processar_reservas_expiradas(
    data_referencia: Optional[datetime] = Query(None), db: Session = Depends(get_db)
):
    return reserva_service.processar_expiracoes(db, data_referencia=data_referencia)


@router.get("", response_model=List[ReservaResponse])
def listar_todas_reservas(
    livro_id: Optional[int] = None,
    usuario_id: Optional[int] = None,
    estado: Optional[EstadoReserva] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    data_referencia: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return reserva_service.list_reservas(
        db,
        livro_id=livro_id,
        usuario_id=usuario_id,
        estado=estado,
        skip=skip,
        limit=limit,
        data_referencia=data_referencia,
    )


@router.get("/{reserva_id}", response_model=ReservaResponse)
def obter_reserva(
    reserva_id: int,
    data_referencia: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return reserva_service.get_reserva(
        db, reserva_id, data_referencia=data_referencia
    )
