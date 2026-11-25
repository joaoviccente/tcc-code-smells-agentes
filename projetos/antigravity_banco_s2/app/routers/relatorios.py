from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.relatorio import (
    RelatorioMovimentacaoResponse,
    RelatorioSaldoNegativoResponse,
    RelatorioReceitaTarifasResponse,
    ProcessarInadimplenciaResponse,
)
from app.services import relatorio_service

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get("/clientes-maior-movimentacao", response_model=RelatorioMovimentacaoResponse, status_code=status.HTTP_200_OK)
def clientes_maior_movimentacao(
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    return relatorio_service.obter_clientes_maior_movimentacao(db, data_inicio, data_fim, limit)


@router.get("/contas-saldo-negativo", response_model=RelatorioSaldoNegativoResponse, status_code=status.HTTP_200_OK)
def contas_saldo_negativo(
    data_ref: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return relatorio_service.obter_contas_saldo_negativo(db, data_ref)


@router.get("/receita-tarifas-categoria", response_model=RelatorioReceitaTarifasResponse, status_code=status.HTTP_200_OK)
def receita_tarifas_categoria(db: Session = Depends(get_db)):
    return relatorio_service.obter_receita_tarifas_por_categoria(db)


@router.post("/processar-saldo-negativo-prolongado", response_model=ProcessarInadimplenciaResponse, status_code=status.HTTP_200_OK)
def processar_saldo_negativo_prolongado(
    data_ref: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return relatorio_service.processar_saldo_negativo_prolongado(db, data_ref)
