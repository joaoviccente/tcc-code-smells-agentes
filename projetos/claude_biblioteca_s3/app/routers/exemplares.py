from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.deps import garantir_unico, get_db
from app.enums import EstadoExemplar
from app.erros import ErroNegocio
from app.models import Exemplar, Livro, Reserva
from app.schemas import ExemplarAtualizar, ExemplarCriar, ExemplarSaida
from app.servicos import (
    alterar_estado_exemplar,
    liberar_exemplar,
    obter,
    verificar_cancelamento_reservas,
)

router = APIRouter(prefix="/exemplares", tags=["Exemplares"])

ESTADOS_INICIAIS = {EstadoExemplar.DISPONIVEL, EstadoExemplar.EM_REPARO, EstadoExemplar.BAIXADO}


@router.post("", response_model=ExemplarSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: ExemplarCriar, db: Session = Depends(get_db)):
    obter(db, Livro, dados.livro_id, "Livro")
    garantir_unico(db, Exemplar, "tombo", dados.tombo)
    if dados.estado not in ESTADOS_INICIAIS:
        raise ErroNegocio("Exemplar novo deve estar 'disponivel', 'em_reparo' ou 'baixado'",
                          status.HTTP_422_UNPROCESSABLE_CONTENT)
    exemplar = Exemplar(livro_id=dados.livro_id, tombo=dados.tombo, estado=dados.estado)
    db.add(exemplar)
    db.flush()
    if exemplar.estado == EstadoExemplar.DISPONIVEL:
        liberar_exemplar(db, exemplar, clock.agora())  # atende a fila, se houver
    db.commit()
    return exemplar


@router.get("", response_model=list[ExemplarSaida])
def listar(livro_id: int | None = None, estado: EstadoExemplar | None = None,
           offset: int = Query(0, ge=0), limite: int = Query(100, ge=1, le=500),
           db: Session = Depends(get_db)):
    q = select(Exemplar).order_by(Exemplar.id)
    if livro_id is not None:
        q = q.where(Exemplar.livro_id == livro_id)
    if estado:
        q = q.where(Exemplar.estado == estado)
    return db.scalars(q.offset(offset).limit(limite)).all()


@router.get("/{exemplar_id}", response_model=ExemplarSaida)
def detalhar(exemplar_id: int, db: Session = Depends(get_db)):
    return obter(db, Exemplar, exemplar_id, "Exemplar")


@router.api_route("/{exemplar_id}", methods=["PUT", "PATCH"], response_model=ExemplarSaida)
def atualizar(exemplar_id: int, dados: ExemplarAtualizar, db: Session = Depends(get_db)):
    """Atualiza tombo e/ou estado. Estados 'emprestado' e 'reservado' sao controlados pelo sistema."""
    exemplar: Exemplar = obter(db, Exemplar, exemplar_id, "Exemplar")
    campos = dados.model_dump(exclude_unset=True)
    if any(v is None for v in campos.values()):
        raise ErroNegocio("Campos nao podem ser nulos", status.HTTP_422_UNPROCESSABLE_CONTENT)
    if "tombo" in campos:
        garantir_unico(db, Exemplar, "tombo", campos["tombo"], exemplar.id)
        exemplar.tombo = campos["tombo"]
    if "estado" in campos:
        alterar_estado_exemplar(db, exemplar, campos["estado"])
    db.commit()
    return exemplar


@router.delete("/{exemplar_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(exemplar_id: int, db: Session = Depends(get_db)):
    exemplar: Exemplar = obter(db, Exemplar, exemplar_id, "Exemplar")
    vinculado = db.scalars(select(Reserva).where(Reserva.exemplar_id == exemplar.id)).first()
    if exemplar.emprestimos or vinculado is not None:
        raise ErroNegocio("Exemplar possui historico de emprestimos/reservas; utilize o estado 'baixado'")
    livro_id = exemplar.livro_id
    db.delete(exemplar)
    db.flush()
    verificar_cancelamento_reservas(db, livro_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
