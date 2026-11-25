from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import garantir_unico, get_db
from ..erros import ErroNegocio
from ..models import Emprestimo, Exemplar, Livro, Reserva
from ..schemas import ExemplarAtualizar, ExemplarCriar, ExemplarSaida
from ..servicos import alocar_exemplar, alterar_estado_exemplar, obter

router = APIRouter(prefix="/exemplares", tags=["Exemplares"])


@router.post("", response_model=ExemplarSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: ExemplarCriar, db: Session = Depends(get_db)):
    obter(db, Livro, dados.livro_id, "Livro")
    garantir_unico(db, Exemplar, "codigo_tombo", dados.codigo_tombo)
    ex = Exemplar(**dados.model_dump())
    db.add(ex)
    if ex.estado == "disponivel":
        alocar_exemplar(db, ex)  # atende a fila de reservas, se houver
    db.commit()
    return ex


@router.get("", response_model=list[ExemplarSaida])
def listar(
    livro_id: int | None = None,
    estado: str | None = Query(None, pattern="^(disponivel|emprestado|reservado|em_reparo|baixado)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Exemplar).order_by(Exemplar.id)
    if livro_id is not None:
        q = q.where(Exemplar.livro_id == livro_id)
    if estado:
        q = q.where(Exemplar.estado == estado)
    return db.scalars(q.offset(skip).limit(limit)).all()


@router.get("/{exemplar_id}", response_model=ExemplarSaida)
def detalhar(exemplar_id: int, db: Session = Depends(get_db)):
    return obter(db, Exemplar, exemplar_id, "Exemplar")


def _atualizar(exemplar_id: int, valores: dict, db: Session):
    ex = obter(db, Exemplar, exemplar_id, "Exemplar")
    if valores.get("codigo_tombo"):
        garantir_unico(db, Exemplar, "codigo_tombo", valores["codigo_tombo"], ex.id)
        ex.codigo_tombo = valores["codigo_tombo"]
    if valores.get("estado"):
        alterar_estado_exemplar(db, ex, valores["estado"])
    db.commit()
    return ex


@router.put("/{exemplar_id}", response_model=ExemplarSaida)
def substituir(exemplar_id: int, dados: ExemplarAtualizar, db: Session = Depends(get_db)):
    if dados.codigo_tombo is None or dados.estado is None:
        raise ErroNegocio("PUT exige codigo_tombo e estado", 422, "validacao")
    return _atualizar(exemplar_id, dados.model_dump(), db)


@router.patch("/{exemplar_id}", response_model=ExemplarSaida)
def atualizar(exemplar_id: int, dados: ExemplarAtualizar, db: Session = Depends(get_db)):
    return _atualizar(exemplar_id, dados.model_dump(exclude_unset=True), db)


@router.delete("/{exemplar_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(exemplar_id: int, db: Session = Depends(get_db)):
    ex = obter(db, Exemplar, exemplar_id, "Exemplar")
    n_emp = db.scalar(select(func.count()).select_from(Emprestimo).where(Emprestimo.exemplar_id == ex.id))
    n_res = db.scalar(select(func.count()).select_from(Reserva).where(Reserva.exemplar_id == ex.id))
    if n_emp or n_res:
        raise ErroNegocio("Exemplar possui historico; use a baixa (estado=baixado) em vez de remover",
                          409, "possui_historico")
    db.delete(ex)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
