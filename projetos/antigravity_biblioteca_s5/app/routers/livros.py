from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.livro import LivroCreate, LivroResponse, LivroUpdate
from app.services import livro_service

router = APIRouter(prefix="/livros", tags=["Livros"])


@router.post("", response_model=LivroResponse, status_code=status.HTTP_201_CREATED)
def criar_livro(livro_in: LivroCreate, db: Session = Depends(get_db)):
    return livro_service.criar_livro(db, livro_in)


@router.get("", response_model=list[LivroResponse])
def listar_livros(
    titulo: str | None = None,
    autor: str | None = None,
    isbn: str | None = None,
    area_conhecimento: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return livro_service.listar_livros(
        db,
        titulo=titulo,
        autor=autor,
        isbn=isbn,
        area_conhecimento=area_conhecimento,
        skip=skip,
        limit=limit,
    )


@router.get("/{livro_id}", response_model=LivroResponse)
def obter_livro(livro_id: int, db: Session = Depends(get_db)):
    return livro_service.obter_livro_por_id(db, livro_id)


@router.put("/{livro_id}", response_model=LivroResponse)
def atualizar_livro(
    livro_id: int,
    livro_in: LivroUpdate,
    db: Session = Depends(get_db),
):
    return livro_service.atualizar_livro(db, livro_id, livro_in)


@router.delete("/{livro_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_livro(livro_id: int, db: Session = Depends(get_db)):
    livro_service.deletar_livro(db, livro_id)
    return None
