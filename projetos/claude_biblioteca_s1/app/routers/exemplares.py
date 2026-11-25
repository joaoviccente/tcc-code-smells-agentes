from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import servicos
from app.deps import get_db
from app.models import EstadoExemplar, Exemplar
from app.schemas import ExemplarAtualizar, ExemplarCriar, ExemplarSaida, ExemplarSubstituir

router = APIRouter(prefix="/exemplares", tags=["Exemplares"])


@router.post("", response_model=ExemplarSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: ExemplarCriar, db: Session = Depends(get_db)):
    return servicos.criar_exemplar(db, dados.model_dump())


@router.get("", response_model=list[ExemplarSaida])
def listar(livro_id: int | None = None, estado: EstadoExemplar | None = None,
           offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    q = select(Exemplar).order_by(Exemplar.id)
    if livro_id is not None:
        q = q.where(Exemplar.livro_id == livro_id)
    if estado:
        q = q.where(Exemplar.estado == estado)
    return db.scalars(q.offset(offset).limit(limit)).all()


@router.get("/{exemplar_id}", response_model=ExemplarSaida)
def detalhar(exemplar_id: int, db: Session = Depends(get_db)):
    return servicos.obter(db, Exemplar, exemplar_id, "Exemplar")


@router.put("/{exemplar_id}", response_model=ExemplarSaida)
def substituir(exemplar_id: int, dados: ExemplarSubstituir, db: Session = Depends(get_db)):
    exemplar = servicos.obter(db, Exemplar, exemplar_id, "Exemplar")
    return servicos.atualizar_exemplar(db, exemplar, dados.model_dump())


@router.patch("/{exemplar_id}", response_model=ExemplarSaida)
def atualizar(exemplar_id: int, dados: ExemplarAtualizar, db: Session = Depends(get_db)):
    exemplar = servicos.obter(db, Exemplar, exemplar_id, "Exemplar")
    return servicos.atualizar_exemplar(db, exemplar, dados.model_dump(exclude_unset=True, exclude_none=True))


@router.delete("/{exemplar_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir(exemplar_id: int, db: Session = Depends(get_db)):
    servicos.excluir_exemplar(db, servicos.obter(db, Exemplar, exemplar_id, "Exemplar"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
