from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import EstadoExemplar
from app.models.exemplar import Exemplar
from app.models.livro import Livro
from app.schemas.livro import LivroCreate, LivroUpdate


def criar_livro(db: Session, livro_in: LivroCreate) -> Livro:
    if db.query(Livro).filter(Livro.isbn == livro_in.isbn).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Livro com ISBN '{livro_in.isbn}' já cadastrado.",
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


def listar_livros(
    db: Session,
    titulo: str | None = None,
    autor: str | None = None,
    isbn: str | None = None,
    area_conhecimento: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Livro]:
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


def obter_livro_por_id(db: Session, livro_id: int) -> Livro:
    livro = db.query(Livro).filter(Livro.id == livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {livro_id} não encontrado.",
        )
    return livro


def atualizar_livro(db: Session, livro_id: int, livro_in: LivroUpdate) -> Livro:
    livro = obter_livro_por_id(db, livro_id)

    if livro_in.isbn and livro_in.isbn != livro.isbn:
        if db.query(Livro).filter(Livro.isbn == livro_in.isbn).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Livro com ISBN '{livro_in.isbn}' já cadastrado.",
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


def deletar_livro(db: Session, livro_id: int) -> None:
    livro = obter_livro_por_id(db, livro_id)

    # Verifica se algum exemplar está emprestado
    exemplares_emprestados = (
        db.query(Exemplar)
        .filter(
            Exemplar.livro_id == livro_id,
            Exemplar.estado == EstadoExemplar.EMPRESTADO,
        )
        .count()
    )
    if exemplares_emprestados > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir livro com exemplares atualmente emprestados.",
        )

    db.delete(livro)
    db.commit()
