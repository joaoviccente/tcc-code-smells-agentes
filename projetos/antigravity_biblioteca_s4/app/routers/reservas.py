from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import EstadoReserva
from app.schemas.reserva import ReservaCreate, ReservaResponse
from app.services import reserva_service

router = APIRouter(prefix="/reservas", tags=["Reservas"])


@router.post("", response_model=ReservaResponse, status_code=status.HTTP_201_CREATED)
def criar_reserva(reserva_in: ReservaCreate, db: Session = Depends(get_db)):
    """Cria uma nova reserva e a adiciona à fila de espera do livro."""
    return reserva_service.create_reserva(db, reserva_in)


@router.post("/{id}/cancelar", response_model=ReservaResponse, status_code=status.HTTP_200_OK)
def cancelar_reserva(id: int, db: Session = Depends(get_db)):
    """Cancela uma reserva existente e passa a vez ao próximo da fila se o exemplar estava disponível."""
    return reserva_service.cancelar_reserva(db, id)


@router.get("/livro/{livro_id}", response_model=List[ReservaResponse], status_code=status.HTTP_200_OK)
def listar_fila_do_livro(livro_id: int, db: Session = Depends(get_db)):
    """Listar fila de reservas de um livro."""
    return reserva_service.listar_fila_do_livro(db, livro_id)


@router.get("", response_model=List[ReservaResponse], status_code=status.HTTP_200_OK)
def listar_reservas(
    livro_id: Optional[int] = None,
    usuario_id: Optional[int] = None,
    estado: Optional[EstadoReserva] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return reserva_service.get_reservas(
        db, livro_id=livro_id, usuario_id=usuario_id, estado=estado, skip=skip, limit=limit
    )


@router.get("/{id}", response_model=ReservaResponse, status_code=status.HTTP_200_OK)
def obter_reserva(id: int, db: Session = Depends(get_db)):
    return reserva_service.get_reserva_by_id(db, id)


@router.post("/processar-expiracoes", response_model=List[ReservaResponse], status_code=status.HTTP_200_OK)
def processar_expiracoes(db: Session = Depends(get_db)):
    """Processa reservas expiradas que ultrapassaram o prazo de 48 horas."""
    return reserva_service.processar_reservas_expiradas(db)
