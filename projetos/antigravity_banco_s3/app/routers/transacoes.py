from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.transacao import (
    DepositoRequest,
    SaqueRequest,
    TransferenciaRequest,
    TransacaoResponse,
)
from app.services.transacao_service import TransacaoService

router = APIRouter(prefix="/transacoes", tags=["Transações"])


@router.post(
    "/deposito",
    response_model=TransacaoResponse,
    status_code=status.HTTP_201_CREATED,
)
def realizar_deposito(req: DepositoRequest, db: Session = Depends(get_db)):
    return TransacaoService.deposito(db, req)


@router.post(
    "/saque",
    response_model=TransacaoResponse,
    status_code=status.HTTP_201_CREATED,
)
def realizar_saque(req: SaqueRequest, db: Session = Depends(get_db)):
    return TransacaoService.saque(db, req)


@router.post(
    "/transferencia",
    response_model=TransacaoResponse,
    status_code=status.HTTP_201_CREATED,
)
def realizar_transferencia(
    req: TransferenciaRequest, db: Session = Depends(get_db)
):
    return TransacaoService.transferencia(db, req)


@router.post(
    "/{transacao_id}/estorno",
    response_model=TransacaoResponse,
    status_code=status.HTTP_201_CREATED,
)
def realizar_estorno(transacao_id: int, db: Session = Depends(get_db)):
    return TransacaoService.estorno(db, transacao_id)


@router.get("", response_model=List[TransacaoResponse])
def listar_transacoes(
    conta_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return TransacaoService.list(db, conta_id=conta_id, skip=skip, limit=limit)


@router.get("/{transacao_id}", response_model=TransacaoResponse)
def obter_transacao(transacao_id: int, db: Session = Depends(get_db)):
    return TransacaoService.get_by_id(db, transacao_id)
