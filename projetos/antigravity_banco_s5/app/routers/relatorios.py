from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.relatorio import (
    ClienteMovimentacaoItem,
    ContaSaldoNegativoItem,
    ReceitaTarifasCategoriaItem,
)
from app.services import relatorio_service

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get(
    "/clientes-maior-movimentacao",
    response_model=List[ClienteMovimentacaoItem],
    status_code=status.HTTP_200_OK,
)
def relatorio_maior_movimentacao(
    data_inicio: Optional[datetime] = Query(None, description="Data/hora inicial do período (ISO)"),
    data_fim: Optional[datetime] = Query(None, description="Data/hora final do período (ISO)"),
    limite: int = Query(10, ge=1, le=100, description="Quantidade máxima de clientes a retornar"),
    db: Session = Depends(get_db),
):
    """
    Relatório: clientes com maior movimentação financeira no período informado.
    Agrupa o total transacionado (depósitos, saques, transferências) por cliente.
    """
    return relatorio_service.relatorio_clientes_maior_movimentacao(
        db, data_inicio=data_inicio, data_fim=data_fim, limite=limite
    )


@router.get(
    "/contas-saldo-negativo",
    response_model=List[ContaSaldoNegativoItem],
    status_code=status.HTTP_200_OK,
)
def relatorio_contas_negativas(db: Session = Depends(get_db)):
    """
    Relatório: lista todas as contas que estão com saldo negativo no momento,
    informando titular, categoria, limite e tempo de saldo negativo.
    """
    return relatorio_service.relatorio_contas_saldo_negativo(db)


@router.get(
    "/receita-tarifas-categoria",
    response_model=List[ReceitaTarifasCategoriaItem],
    status_code=status.HTTP_200_OK,
)
def relatorio_receita_tarifas(db: Session = Depends(get_db)):
    """
    Relatório: receita consolidada de tarifas cobradas agrupada por categoria de cliente
    (comum, premium, empresarial).
    """
    return relatorio_service.relatorio_receita_tarifas_categoria(db)
