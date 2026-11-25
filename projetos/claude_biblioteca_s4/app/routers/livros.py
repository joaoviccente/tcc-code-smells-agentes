from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..apresentacao import reserva_saida
from ..deps import get_db
from ..models import Exemplar, Livro
from ..schemas import ExemplarSaida, LivroAtualizar, LivroCriar, LivroSaida, ReservaSaida
from ..servicos import conflito, fila_reservas, obter

router = APIRouter(prefix="/livros", tags=["Livros"])


def _verificar_isbn(db: Session, isbn: str | None, ignorar_id: int | None = None):
    if isbn is None:
        return
    q = select(Livro.id).where(Livro.isbn == isbn)
    if ignorar_id is not None:
        q = q.where(Livro.id != ignorar_id)
    if db.scalar(q) is not None:
        raise conflito("ISBN_DUPLICADO", "Ja existe livro com este ISBN")


@router.post("", response_model=LivroSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: LivroCriar, db: Session = Depends(get_db)):
    _verificar_isbn(db, dados.isbn)
    livro = Livro(**dados.model_dump())
    db.add(livro)
    db.commit()
    return livro


@router.get("", response_model=list[LivroSaida])
def listar(
    titulo: str | None = Query(None, min_length=1, max_length=300),
    autor: str | None = Query(None, min_length=1, max_length=200),
    area_conhecimento: str | None = Query(None, min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Livro).order_by(Livro.id)
    if titulo:
        q = q.where(Livro.titulo.ilike(f"%{titulo}%"))
    if autor:
        q = q.where(Livro.autor.ilike(f"%{autor}%"))
    if area_conhecimento:
        q = q.where(func.lower(Livro.area_conhecimento) == area_conhecimento.lower())
    return db.scalars(q.offset(skip).limit(limit)).all()


@router.get("/{livro_id}", response_model=LivroSaida)
def detalhar(livro_id: int, db: Session = Depends(get_db)):
    return obter(db, Livro, livro_id, "Livro")


def _atualizar(livro_id: int, dados, db: Session, parcial: bool):
    livro = obter(db, Livro, livro_id, "Livro")
    valores = dados.model_dump(exclude_unset=parcial)
    _verificar_isbn(db, valores.get("isbn"), ignorar_id=livro.id)
    for k, v in valores.items():
        if v is not None:
            setattr(livro, k, v)
    db.commit()
    return livro


@router.put("/{livro_id}", response_model=LivroSaida)
def substituir(livro_id: int, dados: LivroCriar, db: Session = Depends(get_db)):
    return _atualizar(livro_id, dados, db, parcial=False)


@router.patch("/{livro_id}", response_model=LivroSaida)
def atualizar(livro_id: int, dados: LivroAtualizar, db: Session = Depends(get_db)):
    return _atualizar(livro_id, dados, db, parcial=True)


@router.delete("/{livro_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(livro_id: int, db: Session = Depends(get_db)):
    livro = obter(db, Livro, livro_id, "Livro")
    if db.scalar(select(func.count()).select_from(Exemplar).where(Exemplar.livro_id == livro.id)):
        raise conflito("LIVRO_COM_EXEMPLARES", "Livro possui exemplares cadastrados e nao pode ser removido")
    db.delete(livro)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{livro_id}/exemplares", response_model=list[ExemplarSaida])
def exemplares_do_livro(livro_id: int, db: Session = Depends(get_db)):
    obter(db, Livro, livro_id, "Livro")
    return db.scalars(select(Exemplar).where(Exemplar.livro_id == livro_id).order_by(Exemplar.id)).all()


@router.get("/{livro_id}/reservas", response_model=list[ReservaSaida], tags=["Reservas"])
def fila_do_livro(livro_id: int, db: Session = Depends(get_db)):
    """Fila de reserva do livro, na ordem de atendimento (posicao 1 = proximo a ser atendido)."""
    obter(db, Livro, livro_id, "Livro")
    return [reserva_saida(db, r) for r in fila_reservas(db, livro_id)]
