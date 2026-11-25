from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.cliente import ClienteCreate, ClienteUpdate, ClienteResponse
from app.config import CategoriaCliente, SituacaoCliente
from app.services import cliente_service

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.post("", response_model=ClienteResponse, status_code=status.HTTP_201_CREATED)
def criar_cliente(cliente_in: ClienteCreate, db: Session = Depends(get_db)):
    """Cadastra um novo cliente no sistema."""
    return cliente_service.criar_cliente(db, cliente_in)


@router.get("", response_model=List[ClienteResponse], status_code=status.HTTP_200_OK)
def listar_clientes(
    categoria: Optional[CategoriaCliente] = Query(None, description="Filtrar por categoria"),
    situacao: Optional[SituacaoCliente] = Query(None, description="Filtrar por situação"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Lista todos os clientes com suporte a filtros e paginação."""
    return cliente_service.listar_clientes(db, categoria=categoria, situacao=situacao, skip=skip, limit=limit)


@router.get("/{cliente_id}", response_model=ClienteResponse, status_code=status.HTTP_200_OK)
def obter_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de um cliente específico pelo ID."""
    return cliente_service.obter_cliente_por_id(db, cliente_id)


@router.put("/{cliente_id}", response_model=ClienteResponse, status_code=status.HTTP_200_OK)
def atualizar_cliente(cliente_id: int, cliente_in: ClienteUpdate, db: Session = Depends(get_db)):
    """Atualiza dados cadastrais de um cliente."""
    return cliente_service.atualizar_cliente(db, cliente_id, cliente_in)


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Remove um cliente do sistema se não houver contas ativas vinculadas."""
    cliente_service.remover_cliente(db, cliente_id)
    return None
