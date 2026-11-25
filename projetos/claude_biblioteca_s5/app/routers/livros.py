from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import garantir_unico, get_db
from ..erros import ErroNegocio
from ..models import Exemplar, Livro, Reserva
from ..schemas import ExemplarSaida, LivroAtualizar, LivroCriar, LivroSaida, ReservaSaida
from ..servicos import RESERVA_ATIVA, obter

router = APIRouter(prefix="/livros", tags=["Livros"])


@router.post("", response_model=LivroSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: LivroCriar, db: Session = Depends(get_db)):
    garantir_unico(db, Livro, "isbn", dados.isbn)
    livro = Livro(**dados.model_dump())
    db.add(livro)
    db.commit()
    return livro


@router.get("", response_model=list[LivroSaida])
def listar(
    titulo: str | None = None,
    autor: str | None = None,
    area: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Livro).order_by(Livro.id)
    if titulo:
        q = q.where(Livro.titulo.ilike(f"%{titulo}%"))
    if autor:
        q = q.where(Livro.autor.ilike(f"%{autor}%"))
    if area:
        q = q.where(Livro.area_conhecimento == area)
    return db.scalars(q.offset(skip).limit(limit)).all()


@router.get("/{livro_id}", response_model=LivroSaida)
def detalhar(livro_id: int, db: Session = Depends(get_db)):
    return obter(db, Livro, livro_id, "Livro")


def _atualizar(livro_id: int, valores: dict, db: Session):
    livro = obter(db, Livro, livro_id, "Livro")
    valores = {k: v for k, v in valores.items() if v is not None}
    if "isbn" in valores:
        garantir_unico(db, Livro, "isbn", valores["isbn"], livro.id)
    for k, v in valores.items():
        setattr(livro, k, v)
    db.commit()
    return livro


@router.put("/{livro_id}", response_model=LivroSaida)
def substituir(livro_id: int, dados: LivroCriar, db: Session = Depends(get_db)):
    return _atualizar(livro_id, dados.model_dump(), db)


@router.patch("/{livro_id}", response_model=LivroSaida)
def atualizar(livro_id: int, dados: LivroAtualizar, db: Session = Depends(get_db)):
    return _atualizar(livro_id, dados.model_dump(exclude_unset=True), db)


@router.delete("/{livro_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(livro_id: int, db: Session = Depends(get_db)):
    livro = obter(db, Livro, livro_id, "Livro")
    n_ex = db.scalar(select(func.count()).select_from(Exemplar).where(Exemplar.livro_id == livro.id))
    n_res = db.scalar(select(func.count()).select_from(Reserva).where(Reserva.livro_id == livro.id))
    if n_ex or n_res:
        raise ErroNegocio("Livro possui exemplares ou reservas e nao pode ser removido",
                          409, "possui_vinculos")
    db.delete(livro)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{livro_id}/exemplares", response_model=list[ExemplarSaida])
def exemplares_do_livro(livro_id: int, db: Session = Depends(get_db)):
    obter(db, Livro, livro_id, "Livro")
    return db.scalars(select(Exemplar).where(Exemplar.livro_id == livro_id).order_by(Exemplar.id)).all()


@router.get("/{livro_id}/reservas", response_model=list[ReservaSaida])
def fila_de_reservas(
    livro_id: int,
    incluir_encerradas: bool = Query(False, description="Inclui reservas expiradas, canceladas e atendidas"),
    db: Session = Depends(get_db),
):
    """Fila de reservas do livro, em ordem de chegada."""
    obter(db, Livro, livro_id, "Livro")
    q = select(Reserva).where(Reserva.livro_id == livro_id)
    if not incluir_encerradas:
        q = q.where(Reserva.estado.in_(RESERVA_ATIVA))
    return db.scalars(q.order_by(Reserva.data_reserva, Reserva.id)).all()
