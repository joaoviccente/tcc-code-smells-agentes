from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cliente import CategoriaCliente, SituacaoCliente
from app.schemas.cliente import ClienteCreate, ClienteResponse, ClienteUpdate
from app.services.cliente_service import ClienteService

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.post("", response_model=ClienteResponse, status_code=status.HTTP_201_CREATED)
def criar_cliente(cliente_in: ClienteCreate, db: Session = Depends(get_db)):
    """Cadastra um novo cliente com validação de CPF e unicidade de e-mail e CPF."""
    return ClienteService.criar_cliente(db, cliente_in)


@router.get("", response_model=List[ClienteResponse], status_code=status.HTTP_200_OK)
def listar_clientes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    categoria: Optional[CategoriaCliente] = None,
    situacao: Optional[SituacaoCliente] = None,
    db: Session = Depends(get_db),
):
    """Lista clientes cadastrados com filtros opcionais por categoria e situação."""
    return ClienteService.listar_clientes(
        db,
        skip=skip,
        limit=limit,
        categoria=categoria.value if categoria else None,
        situacao=situacao.value if situacao else None,
    )


@router.get("/{cliente_id}", response_model=ClienteResponse, status_code=status.HTTP_200_OK)
def obter_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Obtém os detalhes de um cliente específico pelo ID."""
    return ClienteService.obter_cliente(db, cliente_id)


@router.put("/{cliente_id}", response_model=ClienteResponse, status_code=status.HTTP_200_OK)
def atualizar_cliente(
    cliente_id: int, cliente_in: ClienteUpdate, db: Session = Depends(get_db)
):
    """Atualiza dados cadastrais de um cliente."""
    return ClienteService.atualizar_cliente(db, cliente_id, cliente_in)


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Remove um cliente cadastrado (somente se não possuir contas com saldo ativo)."""
    ClienteService.deletar_cliente(db, cliente_id)
    return None
