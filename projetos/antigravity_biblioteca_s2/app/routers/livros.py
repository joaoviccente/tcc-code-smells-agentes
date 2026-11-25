from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.livro import LivroCreate, LivroResponse, LivroUpdate
from app.services import livro_service

router = APIRouter(prefix="/livros", tags=["Livros"])


@router.post("", response_model=LivroResponse, status_code=status.HTTP_201_CREATED)
def criar_livro(livro_in: LivroCreate, db: Session = Depends(get_db)):
    return livro_service.create_livro(db, livro_in)


@router.get("", response_model=List[LivroResponse])
def listar_livros(
    titulo: Optional[str] = None,
    autor: Optional[str] = None,
    area_conhecimento: Optional[str] = None,
    isbn: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return livro_service.list_livros(
        db,
        titulo=titulo,
        autor=autor,
        area_conhecimento=area_conhecimento,
        isbn=isbn,
        skip=skip,
        limit=limit,
    )


@router.get("/{livro_id}", response_model=LivroResponse)
def obter_livro(livro_id: int, db: Session = Depends(get_db)):
    return livro_service.get_livro(db, livro_id)


@router.put("/{livro_id}", response_model=LivroResponse)
def atualizar_livro(
    livro_id: int, livro_in: LivroUpdate, db: Session = Depends(get_db)
):
    return livro_service.update_livro(db, livro_id, livro_in)


@router.delete("/{livro_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_livro(livro_id: int, db: Session = Depends(get_db)):
    livro_service.delete_livro(db, livro_id)
    return None
