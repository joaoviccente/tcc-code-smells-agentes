from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import CategoriaCliente, EstadoCartao, EstadoConta, SituacaoCliente
from app.schemas import (
    CartaoAtualizar, CartaoCriar, CartaoOut, ClienteAtualizar, ClienteCriar, ClienteOut,
    ContaAtualizar, ContaCriar, ContaOut, validar_cpf,
)
from app.servicos import cadastros as svc
from app.servicos.comum import obter_cartao, obter_cliente, obter_conta
from app.erros import RegraNegocio

clientes = APIRouter(prefix="/clientes", tags=["Clientes"])
contas = APIRouter(prefix="/contas", tags=["Contas"])
cartoes = APIRouter(prefix="/cartoes", tags=["Cartoes"])


# ------------------------------------------------------------------ clientes

@clientes.post("", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def criar_cliente(dados: ClienteCriar, db: Session = Depends(get_db)):
    return svc.criar_cliente(db, dados)


@clientes.get("", response_model=list[ClienteOut])
def listar_clientes(categoria: Optional[CategoriaCliente] = None,
                    situacao: Optional[SituacaoCliente] = None,
                    cpf: Optional[str] = None,
                    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                    db: Session = Depends(get_db)):
    if cpf:
        try:
            cpf = validar_cpf(cpf)
        except ValueError as e:
            raise RegraNegocio(str(e))
    return svc.listar_clientes(db, categoria, situacao, cpf, offset, limit)


@clientes.get("/{cliente_id}", response_model=ClienteOut)
def obter(cliente_id: int, db: Session = Depends(get_db)):
    return obter_cliente(db, cliente_id)


@clientes.get("/{cliente_id}/contas", response_model=list[ContaOut])
def contas_do_cliente(cliente_id: int, db: Session = Depends(get_db)):
    return obter_cliente(db, cliente_id).contas


@clientes.patch("/{cliente_id}", response_model=ClienteOut)
def atualizar_cliente(cliente_id: int, dados: ClienteAtualizar, db: Session = Depends(get_db)):
    return svc.atualizar_cliente(db, cliente_id, dados)


@clientes.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_cliente(cliente_id: int, db: Session = Depends(get_db)):
    svc.remover_cliente(db, cliente_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------------- contas

@contas.post("", response_model=ContaOut, status_code=status.HTTP_201_CREATED)
def criar_conta(dados: ContaCriar, db: Session = Depends(get_db)):
    return svc.criar_conta(db, dados)


@contas.get("", response_model=list[ContaOut])
def listar_contas(cliente_id: Optional[int] = None, estado: Optional[EstadoConta] = None,
                  offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                  db: Session = Depends(get_db)):
    return svc.listar_contas(db, cliente_id, estado, offset, limit)


@contas.get("/{conta_id}", response_model=ContaOut)
def obter_conta_ep(conta_id: int, db: Session = Depends(get_db)):
    return obter_conta(db, conta_id)


@contas.patch("/{conta_id}", response_model=ContaOut)
def atualizar_conta(conta_id: int, dados: ContaAtualizar, db: Session = Depends(get_db)):
    return svc.atualizar_conta(db, conta_id, dados)


@contas.delete("/{conta_id}", response_model=ContaOut,
               summary="Encerrar conta (exige saldo zero e nenhuma fatura em aberto)")
def encerrar_conta(conta_id: int, db: Session = Depends(get_db)):
    return svc.encerrar_conta(db, conta_id)


@contas.post("/{conta_id}/encerramento", response_model=ContaOut,
             summary="Encerrar conta (equivalente ao DELETE)")
def encerrar_conta_post(conta_id: int, db: Session = Depends(get_db)):
    return svc.encerrar_conta(db, conta_id)


# ------------------------------------------------------------------- cartoes

@cartoes.post("", response_model=CartaoOut, status_code=status.HTTP_201_CREATED)
def criar_cartao(dados: CartaoCriar, db: Session = Depends(get_db)):
    return svc.criar_cartao(db, dados)


@cartoes.get("", response_model=list[CartaoOut])
def listar_cartoes(conta_id: Optional[int] = None, estado: Optional[EstadoCartao] = None,
                   offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                   db: Session = Depends(get_db)):
    return svc.listar_cartoes(db, conta_id, estado, offset, limit)


@cartoes.get("/{cartao_id}", response_model=CartaoOut)
def obter_cartao_ep(cartao_id: int, db: Session = Depends(get_db)):
    return obter_cartao(db, cartao_id)


@cartoes.patch("/{cartao_id}", response_model=CartaoOut)
def atualizar_cartao(cartao_id: int, dados: CartaoAtualizar, db: Session = Depends(get_db)):
    return svc.atualizar_cartao(db, cartao_id, dados)


@cartoes.delete("/{cartao_id}", response_model=CartaoOut, summary="Cancelar cartao")
def cancelar_cartao(cartao_id: int, db: Session = Depends(get_db)):
    return svc.cancelar_cartao(db, cartao_id)
