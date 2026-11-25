from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.relatorio import (
    RelatorioMaiorMovimentacaoResponse,
    RelatorioContasNegativasResponse,
    RelatorioReceitaTarifasResponse,
)
from app.services.relatorio_service import RelatorioService

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get("/clientes-maior-movimentacao", response_model=RelatorioMaiorMovimentacaoResponse)
def relatorio_clientes_maior_movimentacao(
    data_inicio: Optional[datetime] = Query(None, description="Data inicial da movimentação"),
    data_fim: Optional[datetime] = Query(None, description="Data final da movimentação"),
    limit: int = Query(10, ge=1, le=100, description="Limite de clientes no relatório"),
    db: Session = Depends(get_db),
):
    """Relatório ordenado dos clientes com maior movimentação financeira no período."""
    return RelatorioService.clientes_maior_movimentacao(
        db,
        data_inicio=data_inicio,
        data_fim=data_fim,
        limit=limit,
    )


@router.get("/contas-saldo-negativo", response_model=RelatorioContasNegativasResponse)
def relatorio_contas_saldo_negativo(db: Session = Depends(get_db)):
    """Relatório de contas que estão atualmente com saldo negativo e contagem de dias em negativo."""
    return RelatorioService.contas_saldo_negativo(db)


@router.get("/receita-tarifas-por-categoria", response_model=RelatorioReceitaTarifasResponse)
def relatorio_receita_tarifas_por_categoria(db: Session = Depends(get_db)):
    """Relatório da receita de tarifas cobradas discriminadas por categoria de cliente (Comum, Premium, Empresarial)."""
    return RelatorioService.receita_tarifas_por_categoria(db)
