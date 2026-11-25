from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import EstadoExemplar
from app.schemas.exemplar import ExemplarCreate, ExemplarUpdate, ExemplarResponse
from app.services import exemplar_service

router = APIRouter(prefix="/exemplares", tags=["Exemplares"])


@router.post("", response_model=ExemplarResponse, status_code=status.HTTP_201_CREATED)
def criar_exemplar(exemplar_in: ExemplarCreate, db: Session = Depends(get_db)):
    return exemplar_service.create_exemplar(db, exemplar_in)


@router.get("", response_model=List[ExemplarResponse], status_code=status.HTTP_200_OK)
def listar_exemplares(
    livro_id: Optional[int] = None,
    estado: Optional[EstadoExemplar] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return exemplar_service.get_exemplares(db, livro_id=livro_id, estado=estado, skip=skip, limit=limit)


@router.get("/{id}", response_model=ExemplarResponse, status_code=status.HTTP_200_OK)
def obter_exemplar(id: int, db: Session = Depends(get_db)):
    return exemplar_service.get_exemplar_by_id(db, id)


@router.put("/{id}", response_model=ExemplarResponse, status_code=status.HTTP_200_OK)
def atualizar_exemplar(id: int, exemplar_in: ExemplarUpdate, db: Session = Depends(get_db)):
    return exemplar_service.update_exemplar(db, id, exemplar_in)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_exemplar(id: int, db: Session = Depends(get_db)):
    exemplar_service.delete_exemplar(db, id)
    return None
