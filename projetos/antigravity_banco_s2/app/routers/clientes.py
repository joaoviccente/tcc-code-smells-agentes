from typing import Optional, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import CategoriaCliente, SituacaoCliente
from app.schemas.cliente import ClienteCreate, ClienteUpdate, ClienteResponse
from app.services import cliente_service

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.post("", response_model=ClienteResponse, status_code=status.HTTP_201_CREATED)
def criar_cliente(cliente_in: ClienteCreate, db: Session = Depends(get_db)):
    return cliente_service.criar_cliente(db, cliente_in)


@router.get("", response_model=List[ClienteResponse], status_code=status.HTTP_200_OK)
def listar_clientes(
    categoria: Optional[CategoriaCliente] = None,
    situacao: Optional[SituacaoCliente] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return cliente_service.listar_clientes(db, categoria, situacao, skip, limit)


@router.get("/{cliente_id}", response_model=ClienteResponse, status_code=status.HTTP_200_OK)
def obter_cliente(cliente_id: int, db: Session = Depends(get_db)):
    return cliente_service.obter_cliente_por_id(db, cliente_id)


@router.put("/{cliente_id}", response_model=ClienteResponse, status_code=status.HTTP_200_OK)
def atualizar_cliente(
    cliente_id: int,
    cliente_in: ClienteUpdate,
    db: Session = Depends(get_db),
):
    return cliente_service.atualizar_cliente(db, cliente_id, cliente_in)


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_cliente(cliente_id: int, db: Session = Depends(get_db)):
    cliente_service.deletar_cliente(db, cliente_id)
    return None
