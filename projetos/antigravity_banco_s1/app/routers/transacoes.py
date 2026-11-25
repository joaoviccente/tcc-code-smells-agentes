from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.transacao import TipoTransacao
from app.schemas.transacao import (
    DepositoCreate,
    ExtratoResponse,
    SaqueCreate,
    TransacaoResponse,
    TransferenciaCreate,
)
from app.services.transacao_service import TransacaoService

router = APIRouter(tags=["Transações"])


@router.post("/transacoes/deposito", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def realizar_deposito(deposito_in: DepositoCreate, db: Session = Depends(get_db)):
    """Realiza um depósito em conta corrente/poupança."""
    return TransacaoService.realizar_deposito(db, deposito_in)


@router.post("/transacoes/saque", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def realizar_saque(saque_in: SaqueCreate, db: Session = Depends(get_db)):
    """
    Realiza um saque.
    Regra 1: Saque só é permitido em conta ativa, de cliente ativo, respeitando o limite diário acumulado da categoria.
    Regra 2: Saldo pode ficar negativo até o limite de crédito.
    """
    return TransacaoService.realizar_saque(db, saque_in)


@router.post("/transacoes/transferencia", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def realizar_transferencia(
    transf_in: TransferenciaCreate, db: Session = Depends(get_db)
):
    """
    Realiza uma transferência entre contas.
    Regra 1: Permitido em conta ativa, de cliente ativo, respeitando o limite por transferência da categoria.
    Regra 2: Saldo pode ficar negativo até o limite de crédito.
    Regra 3: Transferência entre contas do mesmo cliente é isenta. As demais consomem a franquia de transações isentas da categoria e geram tarifa após esgotadas.
    """
    return TransacaoService.realizar_transferencia(db, transf_in)


@router.post("/transacoes/{transacao_id}/estorno", response_model=TransacaoResponse, status_code=status.HTTP_201_CREATED)
def estornar_transacao(transacao_id: int, db: Session = Depends(get_db)):
    """
    Estorna uma transação previamente efetivada.
    Regra 4: Uma transação efetivada pode ser estornada em até 24 horas.
    O estorno reverte o saldo das contas envolvidas e registra uma nova transação do tipo estorno.
    """
    return TransacaoService.estornar_transacao(db, transacao_id)


@router.get("/contas/{conta_id}/extrato", response_model=ExtratoResponse, status_code=status.HTTP_200_OK)
def obter_extrato(
    conta_id: int,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    tipo: Optional[TipoTransacao] = None,
    db: Session = Depends(get_db),
):
    """Gera o extrato de movimentações de uma conta bancária com filtros opcionais por período e tipo."""
    return TransacaoService.obter_extrato(
        db,
        conta_id=conta_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        tipo=tipo.value if tipo else None,
    )
