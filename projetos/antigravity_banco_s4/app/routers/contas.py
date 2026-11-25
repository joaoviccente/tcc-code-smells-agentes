from typing import List, Optional
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import EstadoConta
from app.schemas.conta import (
    ContaCreate,
    ContaUpdate,
    ContaResponse,
    ContaEncerramentoResponse,
)
from app.services.conta_service import ContaService

router = APIRouter(prefix="/contas", tags=["Contas"])


@router.post("", response_model=ContaResponse, status_code=status.HTTP_201_CREATED)
def criar_conta(conta_in: ContaCreate, db: Session = Depends(get_db)):
    """Cria uma nova conta corrente ou poupança para um cliente ativo."""
    return ContaService.create_conta(db, conta_in)


@router.get("", response_model=List[ContaResponse])
def listar_contas(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoConta] = None,
    db: Session = Depends(get_db),
):
    """Lista contas com filtros opcionais por cliente e estado."""
    return ContaService.get_contas(db, skip=skip, limit=limit, cliente_id=cliente_id, estado=estado)


@router.get("/{conta_id}", response_model=ContaResponse)
def obter_conta(conta_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma conta específica."""
    return ContaService.get_conta(db, conta_id)


@router.put("/{conta_id}", response_model=ContaResponse)
def atualizar_conta(conta_id: int, conta_in: ContaUpdate, db: Session = Depends(get_db)):
    """Atualiza dados de uma conta (tipo, limite de crédito ou estado)."""
    return ContaService.update_conta(db, conta_id, conta_in)


@router.delete("/{conta_id}", response_model=ContaEncerramentoResponse)
def deletar_ou_encerrar_conta(conta_id: int, db: Session = Depends(get_db)):
    """
    Encerra a conta aplicando a Regra 7: exige saldo zero e nenhuma fatura aberta.
    Todos os cartões vinculados são cancelados.
    """
    return ContaService.encerrar_conta(db, conta_id)


@router.post("/{conta_id}/encerrar", response_model=ContaEncerramentoResponse)
def encerrar_conta_explicitamente(conta_id: int, db: Session = Depends(get_db)):
    """
    Endpoint explícito para encerramento de conta.
    Regra 7: exige saldo zero e nenhuma fatura aberta. Cancela todos os cartões.
    """
    return ContaService.encerrar_conta(db, conta_id)
