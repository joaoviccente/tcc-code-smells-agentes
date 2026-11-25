from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.conta import ContaCreate, ContaUpdate, ContaResponse
from app.schemas.transacao import ExtratoResponse
from app.schemas.tarifa import TarifaResponse
from app.config import TipoConta, EstadoConta
from app.services import conta_service, transacao_service, tarifa_service

router = APIRouter(prefix="/contas", tags=["Contas"])


@router.post("", response_model=ContaResponse, status_code=status.HTTP_201_CREATED)
def criar_conta(conta_in: ContaCreate, db: Session = Depends(get_db)):
    """Cria uma nova conta para um cliente."""
    return conta_service.criar_conta(db, conta_in)


@router.get("", response_model=List[ContaResponse], status_code=status.HTTP_200_OK)
def listar_contas(
    cliente_id: Optional[int] = Query(None, description="Filtrar por cliente"),
    tipo: Optional[TipoConta] = Query(None, description="Filtrar por tipo de conta"),
    estado: Optional[EstadoConta] = Query(None, description="Filtrar por estado"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Lista contas cadastradas com suporte a filtros e paginação."""
    return conta_service.listar_contas(db, cliente_id=cliente_id, tipo=tipo, estado=estado, skip=skip, limit=limit)


@router.get("/{conta_id}", response_model=ContaResponse, status_code=status.HTTP_200_OK)
def obter_conta(conta_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma conta específica."""
    return conta_service.obter_conta_por_id(db, conta_id)


@router.put("/{conta_id}", response_model=ContaResponse, status_code=status.HTTP_200_OK)
def atualizar_conta(conta_id: int, conta_in: ContaUpdate, db: Session = Depends(get_db)):
    """Atualiza dados de uma conta (tipo, limite de crédito, estado)."""
    return conta_service.atualizar_conta(db, conta_id, conta_in)


@router.post("/{conta_id}/encerrar", response_model=ContaResponse, status_code=status.HTTP_200_OK)
def encerrar_conta(conta_id: int, db: Session = Depends(get_db)):
    """
    Encerra a conta.
    Exige saldo zero e nenhuma fatura aberta ou atrasada. Todos os cartões são cancelados.
    """
    return conta_service.encerrar_conta(db, conta_id)


@router.get("/{conta_id}/extrato", response_model=ExtratoResponse, status_code=status.HTTP_200_OK)
def extrato_conta(
    conta_id: int,
    data_inicio: Optional[datetime] = Query(None, description="Data/hora inicial do extrato"),
    data_fim: Optional[datetime] = Query(None, description="Data/hora final do extrato"),
    db: Session = Depends(get_db),
):
    """Retorna o extrato das movimentações da conta."""
    return transacao_service.obter_extrato_conta(db, conta_id, data_inicio=data_inicio, data_fim=data_fim)


@router.get("/{conta_id}/tarifas", response_model=List[TarifaResponse], status_code=status.HTTP_200_OK)
def listar_tarifas_conta(conta_id: int, db: Session = Depends(get_db)):
    """Lista as tarifas associadas a uma conta."""
    return tarifa_service.listar_tarifas_por_conta(db, conta_id)


@router.post("/{conta_id}/cobrar-mensalidade", response_model=TarifaResponse, status_code=status.HTTP_200_OK)
def cobrar_tarifa_mensal(conta_id: int, db: Session = Depends(get_db)):
    """Aplica e debita a tarifa mensal conforme a categoria do cliente titular."""
    return tarifa_service.cobrar_tarifa_mensal(db, conta_id)
