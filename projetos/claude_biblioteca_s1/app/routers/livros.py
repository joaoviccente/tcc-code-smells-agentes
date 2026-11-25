from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import servicos
from app.deps import get_db
from app.models import Exemplar, Livro
from app.schemas import ExemplarSaida, LivroAtualizar, LivroCriar, LivroSaida, ReservaSaida

router = APIRouter(prefix="/livros", tags=["Livros"])


@router.post("", response_model=LivroSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: LivroCriar, db: Session = Depends(get_db)):
    return servicos.salvar_livro(db, dados.model_dump())


@router.get("", response_model=list[LivroSaida])
def listar(titulo: str | None = None, autor: str | None = None, area: str | None = None,
           offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    q = select(Livro).order_by(Livro.id)
    if titulo:
        q = q.where(Livro.titulo.ilike(f"%{titulo}%"))
    if autor:
        q = q.where(Livro.autor.ilike(f"%{autor}%"))
    if area:
        q = q.where(Livro.area.ilike(area))
    return db.scalars(q.offset(offset).limit(limit)).all()


@router.get("/{livro_id}", response_model=LivroSaida)
def detalhar(livro_id: int, db: Session = Depends(get_db)):
    return servicos.obter(db, Livro, livro_id, "Livro")


@router.put("/{livro_id}", response_model=LivroSaida)
def substituir(livro_id: int, dados: LivroCriar, db: Session = Depends(get_db)):
    livro = servicos.obter(db, Livro, livro_id, "Livro")
    return servicos.salvar_livro(db, dados.model_dump(), livro)


@router.patch("/{livro_id}", response_model=LivroSaida)
def atualizar(livro_id: int, dados: LivroAtualizar, db: Session = Depends(get_db)):
    livro = servicos.obter(db, Livro, livro_id, "Livro")
    return servicos.salvar_livro(db, dados.model_dump(exclude_unset=True, exclude_none=True), livro)


@router.delete("/{livro_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir(livro_id: int, db: Session = Depends(get_db)):
    servicos.excluir_livro(db, servicos.obter(db, Livro, livro_id, "Livro"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{livro_id}/exemplares", response_model=list[ExemplarSaida])
def exemplares_do_livro(livro_id: int, db: Session = Depends(get_db)):
    servicos.obter(db, Livro, livro_id, "Livro")
    return db.scalars(select(Exemplar).where(Exemplar.livro_id == livro_id).order_by(Exemplar.id)).all()


@router.get("/{livro_id}/reservas", response_model=list[ReservaSaida],
            summary="Fila de reservas do livro (por padrao, apenas reservas ativas em ordem de atendimento)")
def fila_de_reservas(livro_id: int, incluir_encerradas: bool = False, db: Session = Depends(get_db)):
    return servicos.fila_do_livro(db, livro_id, incluir_encerradas)
