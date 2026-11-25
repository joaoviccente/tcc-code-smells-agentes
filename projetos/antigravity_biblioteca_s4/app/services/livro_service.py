from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.livro import Livro
from app.models.enums import EstadoEmprestimo
from app.schemas.livro import LivroCreate, LivroUpdate


def get_livros(
    db: Session,
    titulo: Optional[str] = None,
    autor: Optional[str] = None,
    isbn: Optional[str] = None,
    area_conhecimento: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Livro]:
    query = db.query(Livro)
    if titulo:
        query = query.filter(Livro.titulo.ilike(f"%{titulo}%"))
    if autor:
        query = query.filter(Livro.autor.ilike(f"%{autor}%"))
    if isbn:
        query = query.filter(Livro.isbn == isbn)
    if area_conhecimento:
        query = query.filter(Livro.area_conhecimento.ilike(f"%{area_conhecimento}%"))
    return query.offset(skip).limit(limit).all()


def get_livro_by_id(db: Session, livro_id: int) -> Livro:
    livro = db.query(Livro).filter(Livro.id == livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {livro_id} não encontrado.",
        )
    return livro


def create_livro(db: Session, livro_in: LivroCreate) -> Livro:
    livro = Livro(
        titulo=livro_in.titulo,
        autor=livro_in.autor,
        isbn=livro_in.isbn,
        ano=livro_in.ano,
        area_conhecimento=livro_in.area_conhecimento,
    )
    db.add(livro)
    db.commit()
    db.refresh(livro)
    return livro


def update_livro(db: Session, livro_id: int, livro_in: LivroUpdate) -> Livro:
    livro = get_livro_by_id(db, livro_id)
    if livro_in.titulo is not None:
        livro.titulo = livro_in.titulo
    if livro_in.autor is not None:
        livro.autor = livro_in.autor
    if livro_in.isbn is not None:
        livro.isbn = livro_in.isbn
    if livro_in.ano is not None:
        livro.ano = livro_in.ano
    if livro_in.area_conhecimento is not None:
        livro.area_conhecimento = livro_in.area_conhecimento

    db.commit()
    db.refresh(livro)
    return livro


def delete_livro(db: Session, livro_id: int) -> None:
    livro = get_livro_by_id(db, livro_id)
    # Verificar se algum exemplar está emprestado
    for exemplar in livro.exemplares:
        for emp in exemplar.emprestimos:
            if emp.estado in (EstadoEmprestimo.ATIVO, EstadoEmprestimo.ATRASADO):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Não é possível excluir livro que possui exemplares com empréstimos ativos.",
                )
    db.delete(livro)
    db.commit()
