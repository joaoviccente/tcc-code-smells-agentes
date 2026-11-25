from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.config import EstadoExemplar
from app.database import get_db
from app.schemas.exemplar import ExemplarCreate, ExemplarResponse, ExemplarUpdate
from app.services import exemplar_service

router = APIRouter(prefix="/exemplares", tags=["Exemplares"])


@router.post("", response_model=ExemplarResponse, status_code=status.HTTP_201_CREATED)
def criar_exemplar(exemplar_in: ExemplarCreate, db: Session = Depends(get_db)):
    return exemplar_service.criar_exemplar(db, exemplar_in)


@router.get("", response_model=list[ExemplarResponse])
def listar_exemplares(
    livro_id: int | None = None,
    estado: EstadoExemplar | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return exemplar_service.listar_exemplares(
        db,
        livro_id=livro_id,
        estado=estado,
        skip=skip,
        limit=limit,
    )


@router.get("/{exemplar_id}", response_model=ExemplarResponse)
def obter_exemplar(exemplar_id: int, db: Session = Depends(get_db)):
    return exemplar_service.obter_exemplar_por_id(db, exemplar_id)


@router.put("/{exemplar_id}", response_model=ExemplarResponse)
def atualizar_exemplar(
    exemplar_id: int,
    exemplar_in: ExemplarUpdate,
    db: Session = Depends(get_db),
):
    return exemplar_service.atualizar_exemplar(db, exemplar_id, exemplar_in)


@router.delete("/{exemplar_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_exemplar(exemplar_id: int, db: Session = Depends(get_db)):
    exemplar_service.deletar_exemplar(db, exemplar_id)
    return None
