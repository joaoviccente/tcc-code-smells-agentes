"""Emprestimos, reservas, multas e relatorios."""
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import relatorios, servicos
from app.deps import get_db
from app.enums import EstadoEmprestimo, EstadoMulta, EstadoReserva
from app.erros import ErroNegocio
from app.models import Emprestimo, Multa, Reserva
from app.schemas import (
    EmprestimoCriar,
    EmprestimoSaida,
    LivroMaisEmprestado,
    MultaSaida,
    OcupacaoArea,
    ReservaCriar,
    ReservaSaida,
    UsuarioAtrasos,
)

# ---------------------------------------------------------------- Emprestimos
emprestimos = APIRouter(prefix="/emprestimos", tags=["Emprestimos"])


@emprestimos.post("", response_model=EmprestimoSaida, status_code=status.HTTP_201_CREATED)
def criar_emprestimo(dados: EmprestimoCriar, db: Session = Depends(get_db)):
    emp = servicos.criar_emprestimo(db, dados.usuario_id, dados.exemplar_id)
    db.commit()
    return emp


@emprestimos.get("", response_model=list[EmprestimoSaida])
def listar_emprestimos(usuario_id: int | None = None, estado: EstadoEmprestimo | None = None,
                       offset: int = Query(0, ge=0), limite: int = Query(100, ge=1, le=500),
                       db: Session = Depends(get_db)):
    q = select(Emprestimo).order_by(Emprestimo.id)
    if usuario_id is not None:
        q = q.where(Emprestimo.usuario_id == usuario_id)
    if estado:
        q = q.where(Emprestimo.estado == estado)
    return db.scalars(q.offset(offset).limit(limite)).all()


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
    return emp


# ---------------------------------------------------------------- Reservas
reservas = APIRouter(prefix="/reservas", tags=["Reservas"])


@reservas.post("", response_model=ReservaSaida, status_code=status.HTTP_201_CREATED)
def criar_reserva(dados: ReservaCriar, db: Session = Depends(get_db)):
    r = servicos.criar_reserva(db, dados.usuario_id, dados.livro_id)
    db.commit()
    return r


@reservas.get("", response_model=list[ReservaSaida])
def listar_reservas(livro_id: int | None = None, usuario_id: int | None = None,
                    estado: EstadoReserva | None = None, db: Session = Depends(get_db)):
    q = select(Reserva).order_by(Reserva.id)
    if livro_id is not None:
        q = q.where(Reserva.livro_id == livro_id)
    if usuario_id is not None:
        q = q.where(Reserva.usuario_id == usuario_id)
    if estado:
        q = q.where(Reserva.estado == estado)
    return db.scalars(q).all()


@reservas.get("/{reserva_id}", response_model=ReservaSaida)
def detalhar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    return servicos.obter(db, Reserva, reserva_id, "Reserva")


@reservas.post("/{reserva_id}/cancelamento", response_model=ReservaSaida)
def cancelar(reserva_id: int, db: Session = Depends(get_db)):
    r = servicos.cancelar_reserva(db, reserva_id)
    db.commit()
    return r


@reservas.delete("/{reserva_id}", response_model=ReservaSaida)
def cancelar_via_delete(reserva_id: int, db: Session = Depends(get_db)):
    """Equivalente a POST /reservas/{id}/cancelamento (a reserva e mantida no historico como 'cancelada')."""
    return cancelar(reserva_id, db)


# ---------------------------------------------------------------- Multas
multas = APIRouter(prefix="/multas", tags=["Multas"])


@multas.get("", response_model=list[MultaSaida])
def listar_multas(usuario_id: int | None = None, estado: EstadoMulta | None = None,
                  db: Session = Depends(get_db)):
    q = select(Multa).join(Emprestimo).order_by(Multa.id)
    if usuario_id is not None:
        q = q.where(Emprestimo.usuario_id == usuario_id)
    if estado:
        q = q.where(Multa.estado == estado)
    return db.scalars(q).all()


@multas.get("/{multa_id}", response_model=MultaSaida)
def detalhar_multa(multa_id: int, db: Session = Depends(get_db)):
    return servicos.obter(db, Multa, multa_id, "Multa")


@multas.post("/{multa_id}/pagamento", response_model=MultaSaida)
def pagar(multa_id: int, db: Session = Depends(get_db)):
    m = servicos.pagar_multa(db, multa_id)
    db.commit()
    return m


# ---------------------------------------------------------------- Relatorios
relatorios_router = APIRouter(prefix="/relatorios", tags=["Relatorios"])


def _validar_periodo(inicio: date | None, fim: date | None) -> None:
    if inicio and fim and inicio > fim:
        raise ErroNegocio("'inicio' deve ser anterior ou igual a 'fim'", status.HTTP_422_UNPROCESSABLE_CONTENT)


@relatorios_router.get("/livros-mais-emprestados", response_model=list[LivroMaisEmprestado])
def livros_mais_emprestados(inicio: date, fim: date, limite: int = Query(10, ge=1, le=100),
                            db: Session = Depends(get_db)):
    _validar_periodo(inicio, fim)
    return relatorios.livros_mais_emprestados(db, inicio, fim, limite)


@relatorios_router.get("/usuarios-com-mais-atrasos", response_model=list[UsuarioAtrasos])
def usuarios_com_mais_atrasos(inicio: date | None = None, fim: date | None = None,
                              limite: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    _validar_periodo(inicio, fim)
    return relatorios.usuarios_com_mais_atrasos(db, inicio, fim, limite)


@relatorios_router.get("/ocupacao-por-area", response_model=list[OcupacaoArea])
def ocupacao_por_area(db: Session = Depends(get_db)):
    return relatorios.ocupacao_por_area(db)
