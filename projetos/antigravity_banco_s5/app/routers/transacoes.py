from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.transacao import Transacao
from app.schemas.transacao import (
    DepositoRequest,
    SaqueRequest,
    TransferenciaRequest,
    TransacaoResponse,
)
from app.services import transacao_service

router = APIRouter(prefix="/transacoes", tags=["Transações"])


@router.post("/deposito", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def depositar(req: DepositoRequest, db: Session = Depends(get_db)):
    """Realiza um depósito em conta corrente ou poupança."""
    return transacao_service.realizar_deposito(db, req)


@router.post("/saque", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def sacar(req: SaqueRequest, db: Session = Depends(get_db)):
    """
    Realiza um saque respeitando:
    - Conta ativa e cliente ativo;
    - Limite diário acumulado da categoria;
    - Saldo + limite de crédito da conta.
    """
    return transacao_service.realizar_saque(db, req)


@router.post("/transferencia", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def transferir(req: TransferenciaRequest, db: Session = Depends(get_db)):
    """
    Realiza transferência respeitando:
    - Conta de origem ativa e titular ativo;
    - Limite por transferência da categoria;
    - Isenção para contas do mesmo cliente;
    - Franquia de transações isentas da categoria (e cobrança de tarifa após esgotada);
    - Saldo + limite de crédito da conta.
    """
    return transacao_service.realizar_transferencia(db, req)


@router.post("/{transacao_id}/estorno", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def estornar(transacao_id: int, db: Session = Depends(get_db)):
    """
    Estorna uma transação efetivada em até 24 horas.
    Reverte os saldos e registra uma nova transação de estorno.
    """
    return transacao_service.estornar_transacao(db, transacao_id)


@router.get("/{transacao_id}", response_model=TransacaoResponse, status_code=status.HTTP_200_OK)
def obter_transacao(transacao_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma transação pelo ID."""
    transacao = db.query(Transacao).filter(Transacao.id == transacao_id).first()
    if not transacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transação #{transacao_id} não encontrada.",
        )
    return transacao
