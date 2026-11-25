from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.reserva import Reserva
from app.schemas.reserva import ReservaCreate, ReservaResponse
from app.services import reserva_service

router = APIRouter(prefix="/reservas", tags=["Reservas"])


@router.post("", response_model=ReservaResponse, status_code=status.HTTP_201_CREATED)
def criar_reserva(reserva_in: ReservaCreate, db: Session = Depends(get_db)):
    return reserva_service.criar_reserva(db, reserva_in)


@router.post("/{reserva_id}/cancelar", response_model=ReservaResponse)
def cancelar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    return reserva_service.cancelar_reserva(db, reserva_id)


@router.get("/livro/{livro_id}", response_model=list[ReservaResponse])
def listar_fila_do_livro(livro_id: int, db: Session = Depends(get_db)):
    return reserva_service.listar_fila_livro(db, livro_id)


@router.get("", response_model=list[ReservaResponse])
def listar_todas_reservas(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    reserva_service.processar_expiracoes_reservas(db)
    return db.query(Reserva).order_by(Reserva.data_reserva.desc()).offset(skip).limit(limit).all()
