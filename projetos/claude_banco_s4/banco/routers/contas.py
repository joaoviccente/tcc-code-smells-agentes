from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..enums import EstadoConta, EstadoTarifa, TipoTarifa
from ..errors import RegraViolada
from ..models import Tarifa
from ..schemas import CartaoOut, ContaCreate, ContaOut, ContaUpdate, ExtratoOut, TarifaOut
from ..services import cadastros, transacoes
from ..services.comum import obter_conta

router = APIRouter(prefix="/contas", tags=["Contas"])


@router.post("", response_model=ContaOut, status_code=status.HTTP_201_CREATED)
def criar(dados: ContaCreate, db: Session = Depends(get_db)):
    return cadastros.criar_conta(db, dados)


@router.get("", response_model=list[ContaOut])
def listar(
    cliente_id: int | None = None,
    estado: EstadoConta | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return cadastros.listar_contas(db, cliente_id, estado, skip, limit)


@router.get("/{conta_id}", response_model=ContaOut)
def obter(conta_id: int, db: Session = Depends(get_db)):
    return obter_conta(db, conta_id)


@router.patch("/{conta_id}", response_model=ContaOut)
def atualizar(conta_id: int, dados: ContaUpdate, db: Session = Depends(get_db)):
    """Altera limite de credito e/ou estado (ativa/bloqueada)."""
    return cadastros.atualizar_conta(db, conta_id, dados)


@router.delete("/{conta_id}", response_model=ContaOut, summary="Encerrar conta")
def encerrar(conta_id: int, db: Session = Depends(get_db)):
    """Encerra a conta (exige saldo zero e nenhuma fatura em aberto) e cancela seus cartoes."""
    return cadastros.encerrar_conta(db, conta_id)


@router.get("/{conta_id}/cartoes", response_model=list[CartaoOut])
def cartoes_da_conta(conta_id: int, db: Session = Depends(get_db)):
    return obter_conta(db, conta_id).cartoes


@router.get("/{conta_id}/extrato", response_model=ExtratoOut, tags=["Transacoes"])
def extrato(
    conta_id: int,
    inicio: datetime | None = None,
    fim: datetime | None = None,
    db: Session = Depends(get_db),
):
    if inicio and fim and inicio > fim:
        raise RegraViolada("'inicio' deve ser anterior a 'fim'")
    conta, itens = transacoes.extrato(db, conta_id, inicio, fim)
    return {
        "conta_id": conta.id,
        "numero": conta.numero,
        "saldo_atual": conta.saldo,
        "limite_credito": conta.limite_credito,
        "inicio": inicio,
        "fim": fim,
        "itens": itens,
    }


@router.get("/{conta_id}/tarifas", response_model=list[TarifaOut], tags=["Tarifas"])
def tarifas(
    conta_id: int,
    estado: EstadoTarifa | None = None,
    tipo: TipoTarifa | None = None,
    competencia: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: Session = Depends(get_db),
):
    conta = obter_conta(db, conta_id)
    q = select(Tarifa).where(Tarifa.conta_id == conta.id).order_by(Tarifa.data, Tarifa.id)
    if estado:
        q = q.where(Tarifa.estado == estado)
    if tipo:
        q = q.where(Tarifa.tipo == tipo)
    if competencia:
        q = q.where(Tarifa.competencia == competencia)
    return list(db.scalars(q))
