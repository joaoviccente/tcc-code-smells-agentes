from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import EstadoExemplar
from app.schemas.exemplar import ExemplarCreate, ExemplarUpdate, ExemplarResponse
from app.services import exemplar_service

router = APIRouter(prefix="/exemplares", tags=["Exemplares"])


@router.post("", response_model=ExemplarResponse, status_code=status.HTTP_201_CREATED)
def cadastrar_exemplar(exemplar_in: ExemplarCreate, db: Session = Depends(get_db)):
    """Cadastra um novo exemplar de livro no acervo."""
    return exemplar_service.create_exemplar(db, exemplar_in)


@router.get("", response_model=List[ExemplarResponse])
def listar_exemplares(
    livro_id: Optional[int] = Query(None, description="Filtrar por ID do livro"),
    estado: Optional[EstadoExemplar] = Query(None, description="Filtrar por estado do exemplar"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lista exemplares cadastrados."""
    return exemplar_service.get_exemplares(db, livro_id=livro_id, estado=estado, skip=skip, limit=limit)


@router.get("/{id}", response_model=ExemplarResponse)
def obter_exemplar(id: int, db: Session = Depends(get_db)):
    """Obtém dados de um exemplar específico."""
    return exemplar_service.get_exemplar_by_id(db, id)


@router.put("/{id}", response_model=ExemplarResponse)
def atualizar_exemplar(id: int, exemplar_in: ExemplarUpdate, db: Session = Depends(get_db)):
    """Atualiza dados de um exemplar (ex: alterar estado para em_reparo ou baixado)."""
    return exemplar_service.update_exemplar(db, id, exemplar_in)


@router.patch("/{id}", response_model=ExemplarResponse)
def atualizar_exemplar_parcial(id: int, exemplar_in: ExemplarUpdate, db: Session = Depends(get_db)):
    """Atualiza parcialmente dados de um exemplar."""
    return exemplar_service.update_exemplar(db, id, exemplar_in)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_exemplar(id: int, db: Session = Depends(get_db)):
    """Remove um exemplar do acervo."""
    exemplar_service.delete_exemplar(db, id)
    return None
