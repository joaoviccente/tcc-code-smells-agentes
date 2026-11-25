"""Emprestimos, reservas e multas."""
from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Emprestimo, Multa, Reserva
from ..schemas import (
    EmprestimoCriar,
    EmprestimoSaida,
    MultaSaida,
    PagamentoMulta,
    ReservaCriar,
    ReservaSaida,
)
from ..servicos import (
    cancelar_reserva,
    criar_emprestimo,
    criar_reserva,
    devolver_emprestimo,
    obter,
    pagar_multa,
    renovar_emprestimo,
)

emprestimos = APIRouter(prefix="/emprestimos", tags=["emprestimos"])
reservas = APIRouter(prefix="/reservas", tags=["reservas"])
multas = APIRouter(prefix="/multas", tags=["multas"])


# --------------------------------------------------------------------------- emprestimos
@emprestimos.post("", response_model=EmprestimoSaida, status_code=status.HTTP_201_CREATED)
def emprestar(payload: EmprestimoCriar, db: Session = Depends(get_db)):
    emp = criar_emprestimo(db, payload.usuario_id, payload.exemplar_id)
    db.commit()
    return emp


@emprestimos.get("/{emprestimo_id}", response_model=EmprestimoSaida)
def detalhar_emprestimo(emprestimo_id: int, db: Session = Depends(get_db)):
    return obter(db, Emprestimo, emprestimo_id, "emprestimo")


@emprestimos.post("/{emprestimo_id}/renovacao", response_model=EmprestimoSaida)
def renovar(emprestimo_id: int, db: Session = Depends(get_db)):
    emp = renovar_emprestimo(db, obter(db, Emprestimo, emprestimo_id, "emprestimo"))
    db.commit()
    return emp


@emprestimos.post("/{emprestimo_id}/devolucao", response_model=EmprestimoSaida)
def devolver(emprestimo_id: int, db: Session = Depends(get_db)):
    emp = devolver_emprestimo(db, obter(db, Emprestimo, emprestimo_id, "emprestimo"))
    db.commit()
    return emp


# --------------------------------------------------------------------------- reservas
@reservas.post("", response_model=ReservaSaida, status_code=status.HTTP_201_CREATED)
def reservar(payload: ReservaCriar, db: Session = Depends(get_db)):
    reserva = criar_reserva(db, payload.usuario_id, payload.livro_id)
    db.commit()
    return reserva


@reservas.get("/{reserva_id}", response_model=ReservaSaida)
def detalhar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    return obter(db, Reserva, reserva_id, "reserva")


@reservas.post("/{reserva_id}/cancelamento", response_model=ReservaSaida)
def cancelar(reserva_id: int, db: Session = Depends(get_db)):
    reserva = cancelar_reserva(db, obter(db, Reserva, reserva_id, "reserva"))
    db.commit()
    return reserva


@reservas.delete("/{reserva_id}", response_model=ReservaSaida)
def cancelar_via_delete(reserva_id: int, db: Session = Depends(get_db)):
    """Alias de POST /reservas/{id}/cancelamento (a reserva e mantida no historico)."""
    return cancelar(reserva_id, db)


# --------------------------------------------------------------------------- multas
@multas.get("/{multa_id}", response_model=MultaSaida)
def detalhar_multa(multa_id: int, db: Session = Depends(get_db)):
    return obter(db, Multa, multa_id, "multa")


@multas.post("/{multa_id}/pagamento", response_model=MultaSaida)
def registrar_pagamento(multa_id: int, payload: PagamentoMulta | None = Body(None),
                        db: Session = Depends(get_db)):
    multa = pagar_multa(db, obter(db, Multa, multa_id, "multa"), payload.valor if payload else None)
    db.commit()
    return multa
