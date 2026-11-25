from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import EstadoReserva
from app.schemas import ReservaCreate, ReservaResponse
import app.services as services

router = APIRouter(prefix="/reservas", tags=["Reservas"])

@router.post("", response_model=ReservaResponse, status_code=status.HTTP_201_CREATED)
def criar_reserva(dados: ReservaCreate, db: Session = Depends(get_db)):
    return services.criar_reserva(
        db,
        usuario_id=dados.usuario_id,
        livro_id=dados.livro_id,
    )

@router.get("", response_model=List[ReservaResponse], status_code=status.HTTP_200_OK)
def listar_reservas(
    livro_id: Optional[int] = None,
    usuario_id: Optional[int] = None,
    estado: Optional[EstadoReserva] = None,
    db: Session = Depends(get_db)
):
    return services.get_reservas(db, livro_id=livro_id, usuario_id=usuario_id, estado=estado)

@router.get("/{reserva_id}", response_model=ReservaResponse, status_code=status.HTTP_200_OK)
def buscar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    return services.get_reserva(db, reserva_id)

@router.post("/{reserva_id}/cancelar", response_model=ReservaResponse, status_code=status.HTTP_200_OK)
def cancelar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    return services.cancelar_reserva(db, reserva_id)

@router.delete("/{reserva_id}", response_model=ReservaResponse, status_code=status.HTTP_200_OK)
def deletar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    return services.cancelar_reserva(db, reserva_id)
