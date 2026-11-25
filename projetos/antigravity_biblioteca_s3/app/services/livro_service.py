from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models import Livro, Exemplar, Emprestimo
from app.schemas.livro import LivroCreate, LivroUpdate


def create_livro(db: Session, livro_in: LivroCreate) -> Livro:
    isbn_clean = livro_in.isbn.strip()
    if db.query(Livro).filter(Livro.isbn == isbn_clean).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Livro com ISBN '{isbn_clean}' já cadastrado."
        )

    db_livro = Livro(
        titulo=livro_in.titulo.strip(),
        autor=livro_in.autor.strip(),
        isbn=isbn_clean,
        ano=livro_in.ano,
        area=livro_in.area.strip(),
    )
    db.add(db_livro)
    db.commit()
    db.refresh(db_livro)
    return db_livro


def get_livro_by_id(db: Session, livro_id: int) -> Livro:
    livro = db.query(Livro).filter(Livro.id == livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {livro_id} não encontrado."
        )
    return livro


def get_livros(
    db: Session,
    area: Optional[str] = None,
    autor: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Livro]:
    query = db.query(Livro)
    if area:
        query = query.filter(Livro.area.ilike(f"%{area}%"))
    if autor:
        query = query.filter(Livro.autor.ilike(f"%{autor}%"))
    return query.offset(skip).limit(limit).all()


def update_livro(db: Session, livro_id: int, livro_in: LivroUpdate) -> Livro:
    livro = get_livro_by_id(db, livro_id)

    if livro_in.isbn is not None and livro_in.isbn.strip() != livro.isbn:
        isbn_novo = livro_in.isbn.strip()
        if db.query(Livro).filter(Livro.isbn == isbn_novo, Livro.id != livro_id).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Livro com ISBN '{isbn_novo}' já cadastrado."
            )
        livro.isbn = isbn_novo

    if livro_in.titulo is not None:
        livro.titulo = livro_in.titulo.strip()
    if livro_in.autor is not None:
        livro.autor = livro_in.autor.strip()
    if livro_in.ano is not None:
        livro.ano = livro_in.ano
    if livro_in.area is not None:
        livro.area = livro_in.area.strip()

    db.commit()
    db.refresh(livro)
    return livro


def delete_livro(db: Session, livro_id: int) -> None:
    livro = get_livro_by_id(db, livro_id)

    # Verificar se algum exemplar está emprestado
    emprestimos_ativos = db.query(Emprestimo).join(Exemplar).filter(
        Exemplar.livro_id == livro_id,
        Emprestimo.data_devolucao.is_(None)
    ).count()
    if emprestimos_ativos > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir livro com exemplares atualmente emprestados."
        )

    db.delete(livro)
    db.commit()
