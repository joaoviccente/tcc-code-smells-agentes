from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app import schemas as s
from app.database import get_db
from app.models import CategoriaCliente, Cartao, Cliente, Conta, EstadoCartao, EstadoConta, SituacaoCliente
from app.services import cadastros as svc
from app.services.base import obter

clientes = APIRouter(prefix="/clientes", tags=["clientes"])
contas = APIRouter(prefix="/contas", tags=["contas"])
cartoes = APIRouter(prefix="/cartoes", tags=["cartoes"])


# ---------- clientes ----------
@clientes.post("", response_model=s.ClienteOut, status_code=status.HTTP_201_CREATED)
def criar_cliente(dados: s.ClienteCreate, db: Session = Depends(get_db)):
    return svc.criar_cliente(db, dados)


@clientes.get("", response_model=list[s.ClienteOut])
def listar_clientes(categoria: CategoriaCliente | None = None, situacao: SituacaoCliente | None = None,
                    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                    db: Session = Depends(get_db)):
    return svc.listar_clientes(db, categoria, situacao, skip, limit)


@clientes.get("/{cliente_id}", response_model=s.ClienteOut)
def obter_cliente(cliente_id: int, db: Session = Depends(get_db)):
    return obter(db, Cliente, cliente_id, "cliente")


@clientes.patch("/{cliente_id}", response_model=s.ClienteOut)
def atualizar_cliente(cliente_id: int, dados: s.ClienteUpdate, db: Session = Depends(get_db)):
    return svc.atualizar_cliente(db, cliente_id, dados)


@clientes.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_cliente(cliente_id: int, db: Session = Depends(get_db)):
    svc.remover_cliente(db, cliente_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@clientes.get("/{cliente_id}/contas", response_model=list[s.ContaOut])
def contas_do_cliente(cliente_id: int, db: Session = Depends(get_db)):
    return obter(db, Cliente, cliente_id, "cliente").contas


# ---------- contas ----------
@contas.post("", response_model=s.ContaOut, status_code=status.HTTP_201_CREATED)
def criar_conta(dados: s.ContaCreate, db: Session = Depends(get_db)):
    return svc.criar_conta(db, dados)


@contas.get("", response_model=list[s.ContaOut])
def listar_contas(cliente_id: int | None = None, estado: EstadoConta | None = None,
                  skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                  db: Session = Depends(get_db)):
    return svc.listar_contas(db, cliente_id, estado, skip, limit)


@contas.get("/{conta_id}", response_model=s.ContaOut)
def obter_conta(conta_id: int, db: Session = Depends(get_db)):
    return obter(db, Conta, conta_id, "conta")


@contas.patch("/{conta_id}", response_model=s.ContaOut)
def atualizar_conta(conta_id: int, dados: s.ContaUpdate, db: Session = Depends(get_db)):
    return svc.atualizar_conta(db, conta_id, dados)


@contas.delete("/{conta_id}", response_model=s.ContaOut, summary="Encerrar conta")
def encerrar_conta(conta_id: int, db: Session = Depends(get_db)):
    """Encerramento (exclusao logica): exige saldo zero e nenhuma fatura em aberto;
    cancela todos os cartoes da conta."""
    return svc.encerrar_conta(db, conta_id)


@contas.post("/{conta_id}/encerramento", response_model=s.ContaOut, summary="Encerrar conta (alias)")
def encerrar_conta_post(conta_id: int, db: Session = Depends(get_db)):
    return svc.encerrar_conta(db, conta_id)


@contas.get("/{conta_id}/cartoes", response_model=list[s.CartaoOut])
def cartoes_da_conta(conta_id: int, db: Session = Depends(get_db)):
    return obter(db, Conta, conta_id, "conta").cartoes


# ---------- cartoes ----------
@cartoes.post("", response_model=s.CartaoOut, status_code=status.HTTP_201_CREATED)
def criar_cartao(dados: s.CartaoCreate, db: Session = Depends(get_db)):
    return svc.criar_cartao(db, dados)


@cartoes.get("", response_model=list[s.CartaoOut])
def listar_cartoes(conta_id: int | None = None, estado: EstadoCartao | None = None,
                   skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                   db: Session = Depends(get_db)):
    return svc.listar_cartoes(db, conta_id, estado, skip, limit)


@cartoes.get("/{cartao_id}", response_model=s.CartaoOut)
def obter_cartao(cartao_id: int, db: Session = Depends(get_db)):
    return obter(db, Cartao, cartao_id, "cartao")


@cartoes.patch("/{cartao_id}", response_model=s.CartaoOut)
def atualizar_cartao(cartao_id: int, dados: s.CartaoUpdate, db: Session = Depends(get_db)):
    return svc.atualizar_cartao(db, cartao_id, dados)


@cartoes.delete("/{cartao_id}", response_model=s.CartaoOut, summary="Cancelar cartao")
def cancelar_cartao(cartao_id: int, db: Session = Depends(get_db)):
    return svc.cancelar_cartao(db, cartao_id)
