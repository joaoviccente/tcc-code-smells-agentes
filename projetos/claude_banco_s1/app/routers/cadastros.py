"""CRUD de clientes, contas e cartoes."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.database import get_db
from app.models import Cartao, Cliente, Conta, Tarifa
from app.schemas import (
    CartaoAtualizar,
    CartaoCriar,
    CartaoSaida,
    ClienteAtualizar,
    ClienteCriar,
    ClienteSaida,
    ContaAtualizar,
    ContaCriar,
    ContaSaida,
    ExtratoSaida,
    MesReferencia,
    TarifaSaida,
)
from app.services import cadastros, transacoes
from app.services.comum import obter

clientes = APIRouter(prefix="/clientes", tags=["Clientes"])
contas = APIRouter(prefix="/contas", tags=["Contas"])
cartoes = APIRouter(prefix="/cartoes", tags=["Cartoes"])


# ---------------- Clientes ----------------
@clientes.post("", response_model=ClienteSaida, status_code=status.HTTP_201_CREATED)
def criar_cliente(dados: ClienteCriar, db: Session = Depends(get_db)):
    return cadastros.criar_cliente(db, dados.model_dump(), clock.agora())


@clientes.get("", response_model=list[ClienteSaida])
def listar_clientes(
    categoria: Literal["comum", "premium", "empresarial"] | None = None,
    situacao: Literal["ativo", "bloqueado"] | None = None,
    db: Session = Depends(get_db),
):
    consulta = select(Cliente).order_by(Cliente.id)
    if categoria:
        consulta = consulta.where(Cliente.categoria == categoria)
    if situacao:
        consulta = consulta.where(Cliente.situacao == situacao)
    return db.scalars(consulta).all()


@clientes.get("/{cliente_id}", response_model=ClienteSaida)
def obter_cliente(cliente_id: int, db: Session = Depends(get_db)):
    return obter(db, Cliente, cliente_id, "Cliente")


@clientes.patch("/{cliente_id}", response_model=ClienteSaida)
def atualizar_cliente(cliente_id: int, dados: ClienteAtualizar, db: Session = Depends(get_db)):
    return cadastros.atualizar_cliente(db, cliente_id, dados.model_dump(exclude_unset=True), clock.agora())


@clientes.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_cliente(cliente_id: int, db: Session = Depends(get_db)):
    cadastros.excluir_cliente(db, cliente_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- Contas ----------------
@contas.post("", response_model=ContaSaida, status_code=status.HTTP_201_CREATED)
def criar_conta(dados: ContaCriar, db: Session = Depends(get_db)):
    return cadastros.criar_conta(db, dados.model_dump(), clock.agora())


@contas.get("", response_model=list[ContaSaida])
def listar_contas(
    cliente_id: int | None = None,
    estado: Literal["ativa", "bloqueada", "encerrada"] | None = None,
    db: Session = Depends(get_db),
):
    consulta = select(Conta).order_by(Conta.id)
    if cliente_id is not None:
        consulta = consulta.where(Conta.cliente_id == cliente_id)
    if estado:
        consulta = consulta.where(Conta.estado == estado)
    return db.scalars(consulta).all()


@contas.get("/{conta_id}", response_model=ContaSaida)
def obter_conta(conta_id: int, db: Session = Depends(get_db)):
    return obter(db, Conta, conta_id, "Conta")


@contas.patch("/{conta_id}", response_model=ContaSaida)
def atualizar_conta(conta_id: int, dados: ContaAtualizar, db: Session = Depends(get_db)):
    return cadastros.atualizar_conta(db, conta_id, dados.model_dump(exclude_unset=True))


@contas.delete("/{conta_id}", response_model=ContaSaida)
@contas.post("/{conta_id}/encerramento", response_model=ContaSaida)
def encerrar_conta(conta_id: int, db: Session = Depends(get_db)):
    """Encerra a conta (regra 7). A conta e mantida para historico, com estado 'encerrada'."""
    return cadastros.encerrar_conta(db, conta_id, clock.agora())


@contas.get("/{conta_id}/extrato", response_model=ExtratoSaida)
def extrato(
    conta_id: int,
    inicio: datetime | None = None,
    fim: datetime | None = None,
    db: Session = Depends(get_db),
):
    return transacoes.extrato(db, conta_id, inicio, fim)


@contas.get("/{conta_id}/tarifas", response_model=list[TarifaSaida], tags=["Tarifas"])
def listar_tarifas(
    conta_id: int,
    estado: Literal["pendente", "cobrada", "isenta"] | None = None,
    mes_referencia: MesReferencia | None = None,
    db: Session = Depends(get_db),
):
    obter(db, Conta, conta_id, "Conta")
    consulta = select(Tarifa).where(Tarifa.conta_id == conta_id).order_by(Tarifa.id)
    if estado:
        consulta = consulta.where(Tarifa.estado == estado)
    if mes_referencia:
        consulta = consulta.where(Tarifa.mes_referencia == mes_referencia)
    return db.scalars(consulta).all()


# ---------------- Cartoes ----------------
@cartoes.post("", response_model=CartaoSaida, status_code=status.HTTP_201_CREATED)
def criar_cartao(dados: CartaoCriar, db: Session = Depends(get_db)):
    return cadastros.criar_cartao(db, dados.model_dump(), clock.agora())


@cartoes.get("", response_model=list[CartaoSaida])
def listar_cartoes(
    conta_id: int | None = None,
    estado: Literal["ativo", "bloqueado", "cancelado"] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    consulta = select(Cartao).order_by(Cartao.id)
    if conta_id is not None:
        consulta = consulta.where(Cartao.conta_id == conta_id)
    if estado:
        consulta = consulta.where(Cartao.estado == estado)
    return db.scalars(consulta).all()


@cartoes.get("/{cartao_id}", response_model=CartaoSaida)
def obter_cartao(cartao_id: int, db: Session = Depends(get_db)):
    return obter(db, Cartao, cartao_id, "Cartao")


@cartoes.patch("/{cartao_id}", response_model=CartaoSaida)
def atualizar_cartao(cartao_id: int, dados: CartaoAtualizar, db: Session = Depends(get_db)):
    return cadastros.atualizar_cartao(db, cartao_id, dados.model_dump(exclude_unset=True), clock.agora())


@cartoes.delete("/{cartao_id}", response_model=CartaoSaida)
def cancelar_cartao(cartao_id: int, db: Session = Depends(get_db)):
    return cadastros.cancelar_cartao(db, cartao_id)
