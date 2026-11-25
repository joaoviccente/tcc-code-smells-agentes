from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.relatorio import (
    RelatorioContasSaldoNegativoResponse,
    RelatorioMovimentacaoResponse,
    RelatorioReceitaTarifasResponse,
)
from app.services.relatorio_service import RelatorioService

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get(
    "/maior-movimentacao",
    response_model=RelatorioMovimentacaoResponse,
    status_code=status.HTTP_200_OK,
)
def relatorio_maior_movimentacao(
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    limite: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Retorna os clientes com maior movimentação financeira no período especificado."""
    return RelatorioService.clientes_maior_movimentacao(
        db, data_inicio=data_inicio, data_fim=data_fim, limite=limite
    )


@router.get(
    "/contas-saldo-negativo",
    response_model=RelatorioContasSaldoNegativoResponse,
    status_code=status.HTTP_200_OK,
)
def relatorio_contas_saldo_negativo(db: Session = Depends(get_db)):
    """Retorna a relação de contas bancárias atualmente com saldo negativo e a quantidade de dias no negativo."""
    return RelatorioService.contas_com_saldo_negativo(db)


@router.get(
    "/receita-tarifas",
    response_model=RelatorioReceitaTarifasResponse,
    status_code=status.HTTP_200_OK,
)
def relatorio_receita_tarifas(db: Session = Depends(get_db)):
    """Retorna o demonstrativo de receita de tarifas arrecadadas discriminado por categoria de cliente."""
    return RelatorioService.receita_tarifas_por_categoria(db)
