from typing import Optional
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.transacao import Transacao
from app.schemas.transacao import (
    DepositoCreate,
    SaqueCreate,
    TransferenciaCreate,
    EstornoCreate,
    TransacaoResponse,
)
from app.services import transacao_service

router = APIRouter(prefix="/transacoes", tags=["Transações"])


@router.post("/deposito", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def realizar_deposito(deposito_in: DepositoCreate, db: Session = Depends(get_db)):
    return transacao_service.realizar_deposito(db, deposito_in)


@router.post("/saque", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def realizar_saque(saque_in: SaqueCreate, db: Session = Depends(get_db)):
    return transacao_service.realizar_saque(db, saque_in)


@router.post("/transferencia", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def realizar_transferencia(transf_in: TransferenciaCreate, db: Session = Depends(get_db)):
    return transacao_service.realizar_transferencia(db, transf_in)


@router.post("/{transacao_id}/estorno", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def estornar_transacao(
    transacao_id: int,
    estorno_in: Optional[EstornoCreate] = None,
    db: Session = Depends(get_db),
):
    motivo = estorno_in.motivo if estorno_in else None
    return transacao_service.estornar_transacao(db, transacao_id, motivo)


@router.get("/{transacao_id}", response_model=TransacaoResponse, status_code=status.HTTP_200_OK)
def obter_transacao(transacao_id: int, db: Session = Depends(get_db)):
    transacao = db.query(Transacao).filter(Transacao.id == transacao_id).first()
    if not transacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transação com ID {transacao_id} não encontrada."
        )
    return transacao
