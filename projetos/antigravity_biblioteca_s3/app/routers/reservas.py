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
    """
    Cria uma nova reserva para um livro na fila de espera por ordem de chegada.
    """
    return reserva_service.create_reserva(db, reserva_in)


@router.post("/{id}/cancelar", response_model=ReservaResponse)
def cancelar_reserva(id: int, db: Session = Depends(get_db)):
    """
    Cancela uma reserva existente e avança a fila caso o livro já estivesse disponível.
    """
    return reserva_service.cancelar_reserva(db, id)


@router.delete("/{id}", response_model=ReservaResponse)
def cancelar_reserva_delete(id: int, db: Session = Depends(get_db)):
    """
    Cancela uma reserva existente (método DELETE alternativo).
    """
    return reserva_service.cancelar_reserva(db, id)


@router.get("/livro/{livro_id}", response_model=List[ReservaResponse])
def listar_fila_de_um_livro(livro_id: int, db: Session = Depends(get_db)):
    """
    Lista a fila de espera ativa para um determinado livro, ordenada pela posição na fila.
    """
    return reserva_service.get_fila_livro(db, livro_id)


@router.get("", response_model=List[ReservaResponse])
def listar_reservas(
    usuario_id: Optional[int] = Query(None),
    livro_id: Optional[int] = Query(None),
    estado: Optional[EstadoReserva] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lista reservas com filtros."""
    return reserva_service.get_reservas(
        db, usuario_id=usuario_id, livro_id=livro_id, estado=estado, skip=skip, limit=limit
    )


@router.get("/{id}", response_model=ReservaResponse)
def obter_reserva(id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma reserva específica."""
    return reserva_service.get_reserva_by_id(db, id)


@router.post("/processar-expiradas", response_model=List[ReservaResponse])
def processar_expiradas(db: Session = Depends(get_db)):
    """
    Rotina para processar reservas expiradas cujo prazo de 48h esgotou,
    passando a vez para o próximo da fila.
    """
    return reserva_service.processar_reservas_expiradas(db)
