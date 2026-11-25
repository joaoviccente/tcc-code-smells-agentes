"""Emprestimos, reservas e multas."""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import servicos
from ..deps import get_db
from ..models import Emprestimo
from ..schemas import EmprestimoCriar, EmprestimoSaida, MultaSaida, ReservaCriar, ReservaSaida

emprestimos = APIRouter(prefix="/emprestimos", tags=["Emprestimos"])
reservas = APIRouter(prefix="/reservas", tags=["Reservas"])
multas = APIRouter(prefix="/multas", tags=["Multas"])


# --------------------------------------------------------------- Emprestimos
@emprestimos.post("", response_model=EmprestimoSaida, status_code=status.HTTP_201_CREATED)
def criar_emprestimo(dados: EmprestimoCriar, db: Session = Depends(get_db)):
    emp = servicos.criar_emprestimo(db, dados.usuario_id, dados.exemplar_id)
    db.commit()
    return emp


@emprestimos.get("", response_model=list[EmprestimoSaida])
def listar_emprestimos(
    usuario_id: int | None = Query(None, gt=0),
    estado: str | None = Query(None, pattern="^(ativo|devolvido|atrasado)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Emprestimo).options(selectinload(Emprestimo.multa)).order_by(Emprestimo.id.desc())
    if usuario_id is not None:
        servicos.obter(db, servicos.Usuario, usuario_id, "Usuario")
        q = q.where(Emprestimo.usuario_id == usuario_id)
    if estado:
        q = q.where(Emprestimo.estado == estado)
    return db.scalars(q.offset(skip).limit(limit)).all()


@emprestimos.get("/{emprestimo_id}", response_model=EmprestimoSaida)
def detalhar_emprestimo(emprestimo_id: int, db: Session = Depends(get_db)):
    return servicos.obter(db, Emprestimo, emprestimo_id, "Emprestimo")


@emprestimos.post("/{emprestimo_id}/renovacao", response_model=EmprestimoSaida)
def renovar(emprestimo_id: int, db: Session = Depends(get_db)):
    emp = servicos.renovar_emprestimo(db, emprestimo_id)
    db.commit()
    return emp


@emprestimos.post("/{emprestimo_id}/devolucao", response_model=EmprestimoSaida)
def devolver(emprestimo_id: int, db: Session = Depends(get_db)):
    emp = servicos.devolver_emprestimo(db, emprestimo_id)
    db.commit()
    db.refresh(emp)
    return emp


# ------------------------------------------------------------------ Reservas
@reservas.post("", response_model=ReservaSaida, status_code=status.HTTP_201_CREATED)
def criar_reserva(dados: ReservaCriar, db: Session = Depends(get_db)):
    r = servicos.criar_reserva(db, dados.usuario_id, dados.livro_id)
    db.commit()
    return r


@reservas.get("/{reserva_id}", response_model=ReservaSaida)
def detalhar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    return servicos.obter(db, servicos.Reserva, reserva_id, "Reserva")


@reservas.post("/{reserva_id}/cancelamento", response_model=ReservaSaida)
def cancelar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    r = servicos.cancelar_reserva(db, reserva_id)
    db.commit()
    return r


# -------------------------------------------------------------------- Multas
@multas.get("/{multa_id}", response_model=MultaSaida)
def detalhar_multa(multa_id: int, db: Session = Depends(get_db)):
    return servicos.obter(db, servicos.Multa, multa_id, "Multa")


@multas.post("/{multa_id}/pagamento", response_model=MultaSaida)
def pagar(multa_id: int, db: Session = Depends(get_db)):
    m = servicos.pagar_multa(db, multa_id)
    db.commit()
    return m
