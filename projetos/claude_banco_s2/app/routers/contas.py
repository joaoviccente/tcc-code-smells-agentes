from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.database import get_db
from app.errors import RegraViolada
from app.models import Conta, EstadoConta, EstadoTarifa, Tarifa, TipoConta
from app.schemas import (
    PADRAO_MES, ContaAtualizar, ContaCriar, ContaSaida, Extrato, LancamentoExtrato,
    TarifaSaida, TransacaoSaida,
)
from app.services import contas as service
from app.services import transacoes as transacoes_service
from app.services.comum import obter

router = APIRouter(prefix="/contas", tags=["Contas"])


@router.post("", response_model=ContaSaida, status_code=status.HTTP_201_CREATED)
def criar_conta(dados: ContaCriar, db: Session = Depends(get_db)):
    return service.criar(db, dados)


@router.get("", response_model=list[ContaSaida])
def listar_contas(
    cliente_id: int | None = None,
    estado: EstadoConta | None = None,
    tipo: TipoConta | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Conta)
    if cliente_id is not None:
        q = q.where(Conta.cliente_id == cliente_id)
    if estado:
        q = q.where(Conta.estado == estado)
    if tipo:
        q = q.where(Conta.tipo == tipo)
    return db.scalars(q.order_by(Conta.id).offset(skip).limit(limit)).all()


@router.get("/{conta_id}", response_model=ContaSaida)
def obter_conta(conta_id: int, db: Session = Depends(get_db)):
    return obter(db, Conta, conta_id, "Conta")


@router.patch("/{conta_id}", response_model=ContaSaida)
def atualizar_conta(conta_id: int, dados: ContaAtualizar, db: Session = Depends(get_db)):
    return service.atualizar(db, obter(db, Conta, conta_id, "Conta"), dados)


@router.delete("/{conta_id}", response_model=ContaSaida, summary="Encerrar conta")
def encerrar_conta(conta_id: int, db: Session = Depends(get_db)):
    """Encerra a conta (exclusao logica, preservando historico). Exige saldo zero e
    nenhuma fatura em aberto; cancela todos os cartoes da conta."""
    return service.encerrar(db, obter(db, Conta, conta_id, "Conta"), clock.agora())


@router.get("/{conta_id}/extrato", response_model=Extrato, tags=["Transacoes"])
def extrato(
    conta_id: int,
    inicio: date | None = None,
    fim: date | None = None,
    db: Session = Depends(get_db),
):
    if inicio and fim and inicio > fim:
        raise RegraViolada("Data inicial posterior a data final")
    conta = obter(db, Conta, conta_id, "Conta")
    transacoes = transacoes_service.extrato(db, conta, inicio, fim)
    lancamentos = [
        LancamentoExtrato(
            **TransacaoSaida.model_validate(t).model_dump(),
            efeito=transacoes_service.efeito_na_conta(t, conta.id),
        )
        for t in transacoes
    ]
    return Extrato(
        conta_id=conta.id, numero=conta.numero, saldo_atual=conta.saldo,
        inicio=inicio, fim=fim, lancamentos=lancamentos,
    )


@router.get("/{conta_id}/tarifas", response_model=list[TarifaSaida], tags=["Tarifas"])
def listar_tarifas(
    conta_id: int,
    estado: EstadoTarifa | None = None,
    competencia: str | None = Query(None, pattern=PADRAO_MES),
    db: Session = Depends(get_db),
):
    obter(db, Conta, conta_id, "Conta")
    q = select(Tarifa).where(Tarifa.conta_id == conta_id)
    if estado:
        q = q.where(Tarifa.estado == estado)
    if competencia:
        q = q.where(Tarifa.competencia == competencia)
    return db.scalars(q.order_by(Tarifa.criada_em, Tarifa.id)).all()
