from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.relatorio import DisciplinaProcuraReport, TaxaReprovacaoReport, OcupacaoDepartamentoReport
from app.services.relatorio_service import RelatorioService

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])

@router.get("/disciplinas-mais-procuradas", response_model=List[DisciplinaProcuraReport])
def relatorio_disciplinas_mais_procuradas(
    semestre: Optional[str] = Query(None, description="Semestre para filtrar (ex: 2026.1)"),
    db: Session = Depends(get_db)
):
    """
    Relatório: disciplinas mais procuradas no semestre.
    """
    return RelatorioService.disciplinas_mais_procuradas(db, semestre)

@router.get("/taxa-reprovacao", response_model=List[TaxaReprovacaoReport])
def relatorio_taxa_reprovacao(
    departamento: Optional[str] = Query(None, description="Filtrar por departamento"),
    db: Session = Depends(get_db)
):
    """
    Relatório: taxa de reprovação por disciplina no histórico acadêmico.
    """
    return RelatorioService.taxa_reprovacao(db, departamento)

@router.get("/ocupacao-departamentos", response_model=List[OcupacaoDepartamentoReport])
def relatorio_ocupacao_departamentos(
    semestre: Optional[str] = Query(None, description="Semestre para filtrar"),
    db: Session = Depends(get_db)
):
    """
    Relatório: ocupação das turmas por departamento.
    """
    return RelatorioService.ocupacao_departamentos(db, semestre)

@router.get("/ocupacao-turmas-departamento", response_model=List[OcupacaoDepartamentoReport])
def relatorio_ocupacao_turmas_departamento(
    semestre: Optional[str] = Query(None, description="Semestre para filtrar"),
    db: Session = Depends(get_db)
):
    """
    Alias para o relatório de ocupação das turmas por departamento.
    """
    return RelatorioService.ocupacao_departamentos(db, semestre)
