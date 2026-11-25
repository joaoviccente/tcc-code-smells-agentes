from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import Paginacao, get_db
from ..enums import ESTADOS_RESERVA_NA_FILA
from ..models import Exemplar, Livro, Reserva
from ..schemas import ExemplarSaida, LivroAtualizar, LivroCriar, LivroSaida, ReservaSaida
from ..servicos import ErroNegocio, fila_do_livro, obter

router = APIRouter(prefix="/livros", tags=["livros"])


def _checar_isbn(db: Session, isbn: str | None, ignorar_id: int | None = None) -> None:
    if isbn is None:
        return
    q = select(Livro.id).where(Livro.isbn == isbn)
    if ignorar_id is not None:
        q = q.where(Livro.id != ignorar_id)
    if db.scalar(q) is not None:
        raise ErroNegocio("ja existe livro com este ISBN")


@router.post("", response_model=LivroSaida, status_code=status.HTTP_201_CREATED)
def criar(payload: LivroCriar, db: Session = Depends(get_db)):
    _checar_isbn(db, payload.isbn)
    livro = Livro(**payload.model_dump())
    db.add(livro)
    db.commit()
    return livro


@router.get("", response_model=list[LivroSaida])
def listar(titulo: str | None = None, autor: str | None = None, area_conhecimento: str | None = None,
           pag: Paginacao = Depends(), db: Session = Depends(get_db)):
    q = select(Livro).order_by(Livro.id)
    if titulo:
        q = q.where(Livro.titulo.ilike(f"%{titulo}%"))
    if autor:
        q = q.where(Livro.autor.ilike(f"%{autor}%"))
    if area_conhecimento:
        q = q.where(Livro.area_conhecimento.ilike(area_conhecimento))
    return list(db.scalars(pag.aplicar(q)))


@router.get("/{livro_id}", response_model=LivroSaida)
def detalhar(livro_id: int, db: Session = Depends(get_db)):
    return obter(db, Livro, livro_id, "livro")


def _atualizar(livro_id: int, dados: dict, db: Session):
    livro = obter(db, Livro, livro_id, "livro")
    _checar_isbn(db, dados.get("isbn"), ignorar_id=livro_id)
    for campo, valor in dados.items():
        setattr(livro, campo, valor)
    db.commit()
    return livro


@router.put("/{livro_id}", response_model=LivroSaida)
def substituir(livro_id: int, payload: LivroCriar, db: Session = Depends(get_db)):
    return _atualizar(livro_id, payload.model_dump(), db)


@router.patch("/{livro_id}", response_model=LivroSaida)
def atualizar(livro_id: int, payload: LivroAtualizar, db: Session = Depends(get_db)):
    dados = payload.model_dump(exclude_unset=True)
    nulos = [k for k, v in dados.items() if v is None]
    if nulos:
        raise ErroNegocio(f"campos nao podem ser nulos: {', '.join(nulos)}", 422)
    return _atualizar(livro_id, dados, db)


@router.delete("/{livro_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(livro_id: int, db: Session = Depends(get_db)):
    livro = obter(db, Livro, livro_id, "livro")
    if db.scalar(select(func.count(Exemplar.id)).where(Exemplar.livro_id == livro_id)) or \
       db.scalar(select(func.count(Reserva.id)).where(Reserva.livro_id == livro_id)):
        raise ErroNegocio("livro possui exemplares ou reservas registrados e nao pode ser removido")
    db.delete(livro)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{livro_id}/exemplares", response_model=list[ExemplarSaida], tags=["exemplares"])
def exemplares_do_livro(livro_id: int, db: Session = Depends(get_db)):
    obter(db, Livro, livro_id, "livro")
    return list(db.scalars(select(Exemplar).where(Exemplar.livro_id == livro_id).order_by(Exemplar.id)))


@router.get("/{livro_id}/reservas", response_model=list[ReservaSaida], tags=["reservas"])
def fila_de_reservas(livro_id: int,
                     historico: bool = Query(False, description="Inclui reservas encerradas"),
                     db: Session = Depends(get_db)):
    """Fila de reservas do livro, em ordem de chegada (posicao 1 = primeiro)."""
    obter(db, Livro, livro_id, "livro")
    if not historico:
        return fila_do_livro(db, livro_id)
    fila = fila_do_livro(db, livro_id)
    encerradas = list(db.scalars(select(Reserva).where(
        Reserva.livro_id == livro_id, Reserva.estado.not_in(ESTADOS_RESERVA_NA_FILA)
    ).order_by(Reserva.data_reserva, Reserva.id)))
    return fila + encerradas
