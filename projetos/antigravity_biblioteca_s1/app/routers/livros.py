from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import LivroCreate, LivroUpdate, LivroResponse, ReservaResponse
import app.services as services

router = APIRouter(prefix="/livros", tags=["Livros"])

@router.post("", response_model=LivroResponse, status_code=status.HTTP_201_CREATED)
def criar_livro(livro: LivroCreate, db: Session = Depends(get_db)):
    return services.criar_livro(db, livro)

@router.get("", response_model=List[LivroResponse], status_code=status.HTTP_200_OK)
def listar_livros(
    area_conhecimento: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return services.get_livros(db, area_conhecimento=area_conhecimento)

@router.get("/{livro_id}", response_model=LivroResponse, status_code=status.HTTP_200_OK)
def buscar_livro(livro_id: int, db: Session = Depends(get_db)):
    return services.get_livro(db, livro_id)

@router.put("/{livro_id}", response_model=LivroResponse, status_code=status.HTTP_200_OK)
def atualizar_livro(livro_id: int, dados: LivroUpdate, db: Session = Depends(get_db)):
    return services.atualizar_livro(db, livro_id, dados)

@router.delete("/{livro_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_livro(livro_id: int, db: Session = Depends(get_db)):
    services.deletar_livro(db, livro_id)
    return None

@router.get("/{livro_id}/reservas", response_model=List[ReservaResponse], status_code=status.HTTP_200_OK)
def listar_fila_reservas_livro(livro_id: int, db: Session = Depends(get_db)):
    """Lista a fila de reservas ativas para o livro especificado."""
    return services.get_reservas_livro(db, livro_id)
