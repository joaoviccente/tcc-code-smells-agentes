from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.database import get_db
from app.models import CategoriaCliente, Cliente, SituacaoCliente
from app.schemas import ClienteAtualizar, ClienteCriar, ClienteSaida
from app.services import clientes as service
from app.services.comum import obter

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.post("", response_model=ClienteSaida, status_code=status.HTTP_201_CREATED)
def criar_cliente(dados: ClienteCriar, db: Session = Depends(get_db)):
    return service.criar(db, dados)


@router.get("", response_model=list[ClienteSaida])
def listar_clientes(
    categoria: CategoriaCliente | None = None,
    situacao: SituacaoCliente | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Cliente)
    if categoria:
        q = q.where(Cliente.categoria == categoria)
    if situacao:
        q = q.where(Cliente.situacao == situacao)
    return db.scalars(q.order_by(Cliente.id).offset(skip).limit(limit)).all()


@router.get("/{cliente_id}", response_model=ClienteSaida)
def obter_cliente(cliente_id: int, db: Session = Depends(get_db)):
    return obter(db, Cliente, cliente_id, "Cliente")


@router.patch("/{cliente_id}", response_model=ClienteSaida)
def atualizar_cliente(cliente_id: int, dados: ClienteAtualizar, db: Session = Depends(get_db)):
    cliente = obter(db, Cliente, cliente_id, "Cliente")
    return service.atualizar(db, cliente, dados, clock.agora())


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_cliente(cliente_id: int, db: Session = Depends(get_db)):
    service.excluir(db, obter(db, Cliente, cliente_id, "Cliente"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
