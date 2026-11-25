from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.emprestimo import Emprestimo
from app.models.enums import EstadoEmprestimo
from app.models.exemplar import Exemplar
from app.models.livro import Livro
from app.schemas.livro import LivroCreate, LivroUpdate


def create_livro(db: Session, livro_in: LivroCreate) -> Livro:
    if db.query(Livro).filter(Livro.isbn == livro_in.isbn).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um livro cadastrado com este ISBN.",
        )

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


def get_livro(db: Session, livro_id: int) -> Livro:
    livro = db.query(Livro).filter(Livro.id == livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {livro_id} não encontrado.",
        )
    return livro


def list_livros(
    db: Session,
    titulo: Optional[str] = None,
    autor: Optional[str] = None,
    area_conhecimento: Optional[str] = None,
    isbn: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Livro]:
    query = db.query(Livro)
    if titulo:
        query = query.filter(Livro.titulo.ilike(f"%{titulo}%"))
    if autor:
        query = query.filter(Livro.autor.ilike(f"%{autor}%"))
    if area_conhecimento:
        query = query.filter(Livro.area_conhecimento.ilike(f"%{area_conhecimento}%"))
    if isbn:
        query = query.filter(Livro.isbn == isbn)
    return query.offset(skip).limit(limit).all()


def update_livro(db: Session, livro_id: int, livro_in: LivroUpdate) -> Livro:
    livro = db.query(Livro).filter(Livro.id == livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {livro_id} não encontrado.",
        )

    if livro_in.isbn and livro_in.isbn != livro.isbn:
        if db.query(Livro).filter(Livro.isbn == livro_in.isbn).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um livro cadastrado com este ISBN.",
            )
        livro.isbn = livro_in.isbn

    if livro_in.titulo is not None:
        livro.titulo = livro_in.titulo
    if livro_in.autor is not None:
        livro.autor = livro_in.autor
    if livro_in.ano is not None:
        livro.ano = livro_in.ano
    if livro_in.area_conhecimento is not None:
        livro.area_conhecimento = livro_in.area_conhecimento

    db.commit()
    db.refresh(livro)
    return livro


def delete_livro(db: Session, livro_id: int) -> None:
    livro = db.query(Livro).filter(Livro.id == livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {livro_id} não encontrado.",
        )

    # Verificar se algum exemplar está emprestado
    tem_emprestimo_ativo = (
        db.query(Emprestimo)
        .join(Exemplar, Emprestimo.exemplar_id == Exemplar.id)
        .filter(
            Exemplar.livro_id == livro_id,
            Emprestimo.estado.in_([EstadoEmprestimo.ATIVO, EstadoEmprestimo.ATRASADO]),
        )
        .first()
    )
    if tem_emprestimo_ativo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir livro com exemplares emprestados.",
        )

    db.delete(livro)
    db.commit()
