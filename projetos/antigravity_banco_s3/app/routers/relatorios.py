from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.relatorio import (
    ClienteMovimentacaoResponse,
    ContaSaldoNegativoResponse,
    ReceitaTarifasCategoriaResponse,
)
from app.services.relatorio_service import RelatorioService

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get(
    "/clientes-maior-movimentacao",
    response_model=List[ClienteMovimentacaoResponse],
)
def relatorio_clientes_maior_movimentacao(
    data_inicio: Optional[datetime] = Query(None, description="Data início período"),
    data_fim: Optional[datetime] = Query(None, description="Data fim período"),
    limit: int = Query(10, ge=1, le=100, description="Quantidade máxima de registros"),
    db: Session = Depends(get_db),
):
    return RelatorioService.clientes_maior_movimentacao(
        db, data_inicio=data_inicio, data_fim=data_fim, limit=limit
    )


@router.get(
    "/contas-saldo-negativo",
    response_model=List[ContaSaldoNegativoResponse],
)
def relatorio_contas_saldo_negativo(db: Session = Depends(get_db)):
    return RelatorioService.contas_saldo_negativo(db)


@router.get(
    "/receita-tarifas-categoria",
    response_model=List[ReceitaTarifasCategoriaResponse],
)
def relatorio_receita_tarifas_categoria(db: Session = Depends(get_db)):
    return RelatorioService.receita_tarifas_categoria(db)
