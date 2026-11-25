from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from ..apresentacao import emprestimo_saida, reserva_saida
from ..deps import get_db
from ..models import Emprestimo, Multa, Reserva
from ..schemas import (
    EmprestimoCriar, EmprestimoSaida, MultaSaida, PagamentoEntrada, ReservaCriar, ReservaSaida,
)
from .. import servicos
from ..servicos import obter
from .usuarios import emprestimos_do_usuario, multas_do_usuario

emprestimos = APIRouter(prefix="/emprestimos", tags=["Emprestimos"])
reservas = APIRouter(prefix="/reservas", tags=["Reservas"])
multas = APIRouter(prefix="/multas", tags=["Multas"])


# ------------------------------------------------------------------ emprestimos
@emprestimos.post("", response_model=EmprestimoSaida, status_code=status.HTTP_201_CREATED)
def criar_emprestimo(dados: EmprestimoCriar, db: Session = Depends(get_db)):
    emp = servicos.criar_emprestimo(db, dados.usuario_id, dados.exemplar_id)
    db.commit()
    return emprestimo_saida(emp)


@emprestimos.get("", response_model=list[EmprestimoSaida])
def listar_emprestimos(
    usuario_id: int = Query(..., gt=0, description="Usuario cujos emprestimos serao listados"),
    db: Session = Depends(get_db),
):
    return emprestimos_do_usuario(usuario_id, None, db)


@emprestimos.get("/{emprestimo_id}", response_model=EmprestimoSaida)
def detalhar_emprestimo(emprestimo_id: int, db: Session = Depends(get_db)):
    return emprestimo_saida(obter(db, Emprestimo, emprestimo_id, "Emprestimo"))


@emprestimos.post("/{emprestimo_id}/renovacao", response_model=EmprestimoSaida)
def renovar(emprestimo_id: int, db: Session = Depends(get_db)):
    emp = servicos.renovar_emprestimo(db, emprestimo_id)
    db.commit()
    return emprestimo_saida(emp)


@emprestimos.post("/{emprestimo_id}/devolucao", response_model=EmprestimoSaida)
def devolver(emprestimo_id: int, db: Session = Depends(get_db)):
    emp = servicos.devolver_emprestimo(db, emprestimo_id)
    db.commit()
    return emprestimo_saida(emp)


# ------------------------------------------------------------------ reservas
@reservas.post("", response_model=ReservaSaida, status_code=status.HTTP_201_CREATED)
def criar_reserva(dados: ReservaCriar, db: Session = Depends(get_db)):
    reserva = servicos.criar_reserva(db, dados.usuario_id, dados.livro_id)
    db.commit()
    return reserva_saida(db, reserva)


@reservas.get("/{reserva_id}", response_model=ReservaSaida)
def detalhar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    return reserva_saida(db, obter(db, Reserva, reserva_id, "Reserva"))


@reservas.post("/{reserva_id}/cancelamento", response_model=ReservaSaida)
def cancelar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    reserva = servicos.cancelar_reserva(db, reserva_id)
    db.commit()
    return reserva_saida(db, reserva)


# ------------------------------------------------------------------ multas
@multas.get("", response_model=list[MultaSaida])
def listar_multas(
    usuario_id: int = Query(..., gt=0, description="Usuario cujas multas serao listadas"),
    db: Session = Depends(get_db),
):
    return multas_do_usuario(usuario_id, None, db)


@multas.get("/{multa_id}", response_model=MultaSaida)
def detalhar_multa(multa_id: int, db: Session = Depends(get_db)):
    return obter(db, Multa, multa_id, "Multa")


@multas.post("/{multa_id}/pagamento", response_model=MultaSaida)
def pagar(multa_id: int, dados: PagamentoEntrada | None = Body(None), db: Session = Depends(get_db)):
    multa = servicos.pagar_multa(db, multa_id, dados.valor if dados else None)
    db.commit()
    return multa
