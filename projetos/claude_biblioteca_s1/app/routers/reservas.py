from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import servicos
from app.deps import get_db
from app.models import Reserva
from app.schemas import ReservaCriar, ReservaSaida

router = APIRouter(prefix="/reservas", tags=["Reservas"])


@router.post("", response_model=ReservaSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: ReservaCriar, db: Session = Depends(get_db)):
    return servicos.criar_reserva(db, dados.usuario_id, dados.livro_id)


@router.get("/{reserva_id}", response_model=ReservaSaida)
def detalhar(reserva_id: int, db: Session = Depends(get_db)):
    return servicos.obter(db, Reserva, reserva_id, "Reserva")


@router.post("/{reserva_id}/cancelamento", response_model=ReservaSaida)
def cancelar(reserva_id: int, db: Session = Depends(get_db)):
    return servicos.cancelar_reserva(db, servicos.obter(db, Reserva, reserva_id, "Reserva"))
