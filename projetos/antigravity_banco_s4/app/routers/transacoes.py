from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.transacao import (
    DepositoRequest,
    SaqueRequest,
    TransferenciaRequest,
    TransacaoResponse,
    ExtratoResponse,
)
from app.services.transacao_service import TransacaoService

router = APIRouter(tags=["Transações"])


@router.post("/transacoes/deposito", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def realizar_deposito(req: DepositoRequest, db: Session = Depends(get_db)):
    """Realiza um depósito em uma conta corrente."""
    return TransacaoService.depositar(db, req)


@router.post("/transacoes/saque", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def realizar_saque(req: SaqueRequest, db: Session = Depends(get_db)):
    """
    Realiza um saque respeitando:
    - Conta ativa e cliente ativo (Regra 1)
    - Limite diário de saque acumulado da categoria (Regra 1)
    - Saldo disponível com limite de crédito (Regra 2)
    """
    return TransacaoService.sacar(db, req)


@router.post("/transacoes/transferencia", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def realizar_transferencia(req: TransferenciaRequest, db: Session = Depends(get_db)):
    """
    Realiza uma transferência respeitando:
    - Conta ativa e cliente ativo (Regra 1)
    - Limite por transferência da categoria (Regra 1)
    - Saldo disponível com limite de crédito (Regra 2)
    - Isenção entre contas do mesmo cliente vs. consumo de franquia e cobrança de tarifas (Regra 3)
    """
    return TransacaoService.transferir(db, req)


@router.post("/transacoes/{transacao_id}/estorno", response_model=TransacaoResponse, status_code=status.HTTP_200_OK)
def realizar_estorno(transacao_id: int, db: Session = Depends(get_db)):
    """
    Realiza o estorno de uma transação efetivada em até 24 horas (Regra 4).
    Reverte os saldos e registra uma nova transação de estorno.
    """
    return TransacaoService.estornar(db, transacao_id)


@router.get("/contas/{conta_id}/extrato", response_model=ExtratoResponse)
@router.get("/transacoes/extrato/{conta_id}", response_model=ExtratoResponse, include_in_schema=False)
def consultar_extrato(
    conta_id: int,
    data_inicio: Optional[datetime] = Query(None, description="Data inicial no formato ISO 8601"),
    data_fim: Optional[datetime] = Query(None, description="Data final no formato ISO 8601"),
    db: Session = Depends(get_db),
):
    """Consulta o extrato detalhado de movimentações da conta."""
    return TransacaoService.get_extrato(db, conta_id, data_inicio=data_inicio, data_fim=data_fim)
