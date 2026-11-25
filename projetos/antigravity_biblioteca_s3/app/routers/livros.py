from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.livro import LivroCreate, LivroUpdate, LivroResponse
from app.services import livro_service

router = APIRouter(prefix="/livros", tags=["Livros"])


@router.post("", response_model=LivroResponse, status_code=status.HTTP_201_CREATED)
def cadastrar_livro(livro_in: LivroCreate, db: Session = Depends(get_db)):
    """Cadastra um novo livro no acervo."""
    return livro_service.create_livro(db, livro_in)


@router.get("", response_model=List[LivroResponse])
def listar_livros(
    area: Optional[str] = Query(None, description="Filtrar por área de conhecimento"),
    autor: Optional[str] = Query(None, description="Filtrar por autor"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lista livros do acervo."""
    return livro_service.get_livros(db, area=area, autor=autor, skip=skip, limit=limit)


@router.get("/{id}", response_model=LivroResponse)
def obter_livro(id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de um livro específico."""
    return livro_service.get_livro_by_id(db, id)


@router.put("/{id}", response_model=LivroResponse)
def atualizar_livro(id: int, livro_in: LivroUpdate, db: Session = Depends(get_db)):
    """Atualiza dados de um livro."""
    return livro_service.update_livro(db, id, livro_in)


@router.patch("/{id}", response_model=LivroResponse)
def atualizar_livro_parcial(id: int, livro_in: LivroUpdate, db: Session = Depends(get_db)):
    """Atualiza parcialmente dados de um livro."""
    return livro_service.update_livro(db, id, livro_in)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_livro(id: int, db: Session = Depends(get_db)):
    """Remove um livro do acervo."""
    livro_service.delete_livro(db, id)
    return None
