from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from ..deps import get_db
from ..models import Emprestimo, Exemplar, Livro, Reserva
from ..schemas import ExemplarAtualizar, ExemplarCriar, ExemplarSaida
from ..servicos import alterar_estado_exemplar, conflito, liberar_exemplar, obter

router = APIRouter(prefix="/exemplares", tags=["Exemplares"])


def _verificar_tombo(db: Session, codigo: str | None, ignorar_id: int | None = None):
    if codigo is None:
        return
    q = select(Exemplar.id).where(func.upper(Exemplar.codigo_tombo) == codigo.upper())
    if ignorar_id is not None:
        q = q.where(Exemplar.id != ignorar_id)
    if db.scalar(q) is not None:
        raise conflito("TOMBO_DUPLICADO", "Ja existe exemplar com este codigo de tombo")


@router.post("", response_model=ExemplarSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: ExemplarCriar, db: Session = Depends(get_db)):
    obter(db, Livro, dados.livro_id, "Livro")
    _verificar_tombo(db, dados.codigo_tombo)
    exemplar = Exemplar(livro_id=dados.livro_id, codigo_tombo=dados.codigo_tombo, estado=dados.estado)
    db.add(exemplar)
    db.flush()
    if dados.estado == "disponivel":
        # Um novo exemplar atende imediatamente a fila de reserva, se houver.
        liberar_exemplar(db, exemplar, clock.agora())
    db.commit()
    return exemplar


@router.get("", response_model=list[ExemplarSaida])
def listar(
    livro_id: int | None = Query(None, gt=0),
    estado: Literal["disponivel", "emprestado", "reservado", "em_reparo", "baixado"] | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Exemplar).order_by(Exemplar.id)
    if livro_id:
        q = q.where(Exemplar.livro_id == livro_id)
    if estado:
        q = q.where(Exemplar.estado == estado)
    return db.scalars(q.offset(skip).limit(limit)).all()


@router.get("/{exemplar_id}", response_model=ExemplarSaida)
def detalhar(exemplar_id: int, db: Session = Depends(get_db)):
    return obter(db, Exemplar, exemplar_id, "Exemplar")


@router.patch("/{exemplar_id}", response_model=ExemplarSaida)
def atualizar(exemplar_id: int, dados: ExemplarAtualizar, db: Session = Depends(get_db)):
    """Altera o tombo e/ou o estado (disponivel, em_reparo, baixado).

    Os estados emprestado e reservado sao gerenciados pelo sistema.
    """
    exemplar = obter(db, Exemplar, exemplar_id, "Exemplar")
    if dados.codigo_tombo is not None:
        _verificar_tombo(db, dados.codigo_tombo, ignorar_id=exemplar.id)
        exemplar.codigo_tombo = dados.codigo_tombo
    if dados.estado is not None:
        alterar_estado_exemplar(db, exemplar, dados.estado)
    db.commit()
    return exemplar


@router.delete("/{exemplar_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(exemplar_id: int, db: Session = Depends(get_db)):
    exemplar = obter(db, Exemplar, exemplar_id, "Exemplar")
    if db.scalar(select(func.count()).select_from(Emprestimo).where(Emprestimo.exemplar_id == exemplar.id)) or \
            db.scalar(select(func.count()).select_from(Reserva).where(Reserva.exemplar_id == exemplar.id)):
        raise conflito(
            "EXEMPLAR_COM_HISTORICO",
            "Exemplar possui historico de circulacao; use o estado 'baixado' em vez de remover",
        )
    db.delete(exemplar)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
