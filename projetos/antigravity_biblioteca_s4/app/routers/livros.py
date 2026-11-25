from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.livro import LivroCreate, LivroUpdate, LivroResponse
from app.schemas.exemplar import ExemplarResponse
from app.schemas.reserva import ReservaResponse
from app.services import livro_service, exemplar_service, reserva_service

router = APIRouter(prefix="/livros", tags=["Livros"])


@router.post("", response_model=LivroResponse, status_code=status.HTTP_201_CREATED)
def criar_livro(livro_in: LivroCreate, db: Session = Depends(get_db)):
    return livro_service.create_livro(db, livro_in)


@router.get("", response_model=List[LivroResponse], status_code=status.HTTP_200_OK)
def listar_livros(
    titulo: Optional[str] = None,
    autor: Optional[str] = None,
    isbn: Optional[str] = None,
    area_conhecimento: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return livro_service.get_livros(
        db,
        titulo=titulo,
        autor=autor,
        isbn=isbn,
        area_conhecimento=area_conhecimento,
        skip=skip,
        limit=limit,
    )


@router.get("/{id}", response_model=LivroResponse, status_code=status.HTTP_200_OK)
def obter_livro(id: int, db: Session = Depends(get_db)):
    return livro_service.get_livro_by_id(db, id)


@router.put("/{id}", response_model=LivroResponse, status_code=status.HTTP_200_OK)
def atualizar_livro(id: int, livro_in: LivroUpdate, db: Session = Depends(get_db)):
    return livro_service.update_livro(db, id, livro_in)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_livro(id: int, db: Session = Depends(get_db)):
    livro_service.delete_livro(db, id)
    return None


@router.get("/{id}/exemplares", response_model=List[ExemplarResponse], status_code=status.HTTP_200_OK)
def listar_exemplares_do_livro(id: int, db: Session = Depends(get_db)):
    livro_service.get_livro_by_id(db, id)
    return exemplar_service.get_exemplares(db, livro_id=id)


@router.get("/{id}/reservas", response_model=List[ReservaResponse], status_code=status.HTTP_200_OK)
def listar_fila_do_livro(id: int, db: Session = Depends(get_db)):
    """Listar fila de reservas de um livro."""
    return reserva_service.listar_fila_do_livro(db, id)
