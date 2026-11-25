from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.conta import EstadoConta
from app.schemas.conta import (
    ContaCreate,
    ContaResponse,
    ContaUpdate,
    EncerramentoContaResponse,
)
from app.services.conta_service import ContaService

router = APIRouter(prefix="/contas", tags=["Contas"])


@router.post("", response_model=ContaResponse, status_code=status.HTTP_201_CREATED)
def criar_conta(conta_in: ContaCreate, db: Session = Depends(get_db)):
    """Abre uma nova conta para um cliente."""
    return ContaService.criar_conta(db, conta_in)


@router.get("", response_model=List[ContaResponse], status_code=status.HTTP_200_OK)
def listar_contas(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoConta] = None,
    db: Session = Depends(get_db),
):
    """Lista contas com filtros opcionais por cliente e estado."""
    return ContaService.listar_contas(
        db,
        skip=skip,
        limit=limit,
        cliente_id=cliente_id,
        estado=estado.value if estado else None,
    )


@router.get("/{conta_id}", response_model=ContaResponse, status_code=status.HTTP_200_OK)
def obter_conta(conta_id: int, db: Session = Depends(get_db)):
    """Obtém os detalhes de uma conta pelo ID."""
    return ContaService.obter_conta(db, conta_id)


@router.put("/{conta_id}", response_model=ContaResponse, status_code=status.HTTP_200_OK)
def atualizar_conta(
    conta_id: int, conta_in: ContaUpdate, db: Session = Depends(get_db)
):
    """Atualiza dados de uma conta (tipo, limite de crédito, estado)."""
    return ContaService.atualizar_conta(db, conta_id, conta_in)


@router.post("/{conta_id}/encerrar", response_model=EncerramentoContaResponse, status_code=status.HTTP_200_OK)
def encerrar_conta(conta_id: int, db: Session = Depends(get_db)):
    """
    Encerra uma conta corrente.
    Regra 7: O encerramento de conta exige saldo zero e nenhuma fatura aberta.
    Ao encerrar, todos os cartões da conta são cancelados.
    """
    return ContaService.encerrar_conta(db, conta_id)


@router.delete("/{conta_id}", response_model=EncerramentoContaResponse, status_code=status.HTTP_200_OK)
def deletar_ou_encerrar_conta(conta_id: int, db: Session = Depends(get_db)):
    """Encerra a conta conforme as regras de negócio bancárias."""
    return ContaService.encerrar_conta(db, conta_id)
