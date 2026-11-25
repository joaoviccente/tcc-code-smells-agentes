from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.conta import ContaCreate, ContaUpdate, ContaResponse
from app.schemas.transacao import ExtratoResponse
from app.schemas.tarifa import TarifaResponse, TarifaCobrarMensalidadeRequest
from app.services.conta_service import ContaService
from app.services.transacao_service import TransacaoService
from app.services.tarifa_service import TarifaService

router = APIRouter(prefix="/contas", tags=["Contas"])


@router.post("", response_model=ContaResponse, status_code=status.HTTP_201_CREATED)
def criar_conta(conta_in: ContaCreate, db: Session = Depends(get_db)):
    return ContaService.create(db, conta_in)


@router.get("", response_model=List[ContaResponse])
def listar_contas(
    cliente_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return ContaService.list(db, cliente_id=cliente_id, skip=skip, limit=limit)


@router.get("/{conta_id}", response_model=ContaResponse)
def obter_conta(conta_id: int, db: Session = Depends(get_db)):
    return ContaService.get_by_id(db, conta_id)


@router.put("/{conta_id}", response_model=ContaResponse)
def atualizar_conta(
    conta_id: int, conta_in: ContaUpdate, db: Session = Depends(get_db)
):
    return ContaService.update(db, conta_id, conta_in)


@router.post("/{conta_id}/encerrar", response_model=ContaResponse)
def encerrar_conta(conta_id: int, db: Session = Depends(get_db)):
    return ContaService.encerrar(db, conta_id)


@router.delete("/{conta_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_conta(conta_id: int, db: Session = Depends(get_db)):
    ContaService.delete(db, conta_id)
    return None


@router.get("/{conta_id}/extrato", response_model=ExtratoResponse)
def obter_extrato(
    conta_id: int,
    data_inicio: Optional[datetime] = Query(None, description="Data de início (ISO)"),
    data_fim: Optional[datetime] = Query(None, description="Data de fim (ISO)"),
    db: Session = Depends(get_db),
):
    return TransacaoService.extrato(
        db, conta_id=conta_id, data_inicio=data_inicio, data_fim=data_fim
    )


@router.get("/{conta_id}/tarifas", response_model=List[TarifaResponse])
def listar_tarifas_conta(
    conta_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return TarifaService.list_by_conta(db, conta_id=conta_id, skip=skip, limit=limit)


@router.post("/{conta_id}/tarifas/cobrar-mensalidade", response_model=TarifaResponse)
def cobrar_tarifa_mensal(
    conta_id: int,
    req: TarifaCobrarMensalidadeRequest = TarifaCobrarMensalidadeRequest(),
    db: Session = Depends(get_db),
):
    return TarifaService.cobrar_mensalidade(db, conta_id=conta_id, req=req)
