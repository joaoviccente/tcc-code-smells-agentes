from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import garantir_unico, get_db
from app.erros import ErroNegocio
from app.models import Exemplar, Livro
from app.schemas import ExemplarSaida, LivroAtualizar, LivroCriar, LivroSaida, ReservaSaida
from app.servicos import fila_do_livro, obter

router = APIRouter(prefix="/livros", tags=["Livros"])


@router.post("", response_model=LivroSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: LivroCriar, db: Session = Depends(get_db)):
    garantir_unico(db, Livro, "isbn", dados.isbn)
    livro = Livro(**dados.model_dump())
    db.add(livro)
    db.commit()
    return livro


@router.get("", response_model=list[LivroSaida])
def listar(area: str | None = None, autor: str | None = None, titulo: str | None = None,
           offset: int = Query(0, ge=0), limite: int = Query(100, ge=1, le=500),
           db: Session = Depends(get_db)):
    q = select(Livro).order_by(Livro.id)
    if area:
        q = q.where(Livro.area == area)
    if autor:
        q = q.where(Livro.autor.ilike(f"%{autor}%"))
    if titulo:
        q = q.where(Livro.titulo.ilike(f"%{titulo}%"))
    return db.scalars(q.offset(offset).limit(limite)).all()


@router.get("/{livro_id}", response_model=LivroSaida)
def detalhar(livro_id: int, db: Session = Depends(get_db)):
    return obter(db, Livro, livro_id, "Livro")


@router.api_route("/{livro_id}", methods=["PUT", "PATCH"], response_model=LivroSaida)
def atualizar(livro_id: int, dados: LivroAtualizar, db: Session = Depends(get_db)):
    livro: Livro = obter(db, Livro, livro_id, "Livro")
    campos = dados.model_dump(exclude_unset=True)
    for campo, valor in campos.items():
        if valor is None:
            raise ErroNegocio(f"Campo '{campo}' nao pode ser nulo", status.HTTP_422_UNPROCESSABLE_CONTENT)
    if "isbn" in campos:
        garantir_unico(db, Livro, "isbn", campos["isbn"], livro.id)
    for campo, valor in campos.items():
        setattr(livro, campo, valor)
    db.commit()
    return livro


@router.delete("/{livro_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(livro_id: int, db: Session = Depends(get_db)):
    livro: Livro = obter(db, Livro, livro_id, "Livro")
    if livro.exemplares or livro.reservas:
        raise ErroNegocio("Livro possui exemplares ou reservas e nao pode ser removido")
    db.delete(livro)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{livro_id}/exemplares", response_model=list[ExemplarSaida], tags=["Exemplares"])
def exemplares_do_livro(livro_id: int, db: Session = Depends(get_db)):
    obter(db, Livro, livro_id, "Livro")
    return db.scalars(select(Exemplar).where(Exemplar.livro_id == livro_id).order_by(Exemplar.id)).all()


@router.get("/{livro_id}/reservas", response_model=list[ReservaSaida], tags=["Reservas"])
def fila_de_reservas(livro_id: int, db: Session = Depends(get_db)):
    """Fila de reservas ativas do livro (disponiveis para retirada primeiro, depois por ordem de chegada)."""
    return fila_do_livro(db, livro_id)
