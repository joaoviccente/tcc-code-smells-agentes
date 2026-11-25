from typing import List, Optional
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import CategoriaCliente, SituacaoCliente
from app.schemas.cliente import ClienteCreate, ClienteUpdate, ClienteResponse
from app.services.cliente_service import ClienteService

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.post("", response_model=ClienteResponse, status_code=status.HTTP_201_CREATED)
def criar_cliente(cliente_in: ClienteCreate, db: Session = Depends(get_db)):
    """Cadastra um novo cliente."""
    return ClienteService.create_cliente(db, cliente_in)


@router.get("", response_model=List[ClienteResponse])
def listar_clientes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    categoria: Optional[CategoriaCliente] = None,
    situacao: Optional[SituacaoCliente] = None,
    db: Session = Depends(get_db),
):
    """Lista clientes com filtros opcionais por categoria e situação."""
    return ClienteService.get_clientes(db, skip=skip, limit=limit, categoria=categoria, situacao=situacao)


@router.get("/{cliente_id}", response_model=ClienteResponse)
def obter_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de um cliente específico."""
    return ClienteService.get_cliente(db, cliente_id)


@router.put("/{cliente_id}", response_model=ClienteResponse)
def atualizar_cliente(cliente_id: int, cliente_in: ClienteUpdate, db: Session = Depends(get_db)):
    """Atualiza dados cadastrais de um cliente."""
    return ClienteService.update_cliente(db, cliente_id, cliente_in)


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Remove um cliente se todas as suas contas estiverem encerradas."""
    ClienteService.delete_cliente(db, cliente_id)
    return None
