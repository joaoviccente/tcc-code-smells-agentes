from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.relatorios import (
    DisciplinaMaisProcuradaResponse,
    TaxaReprovacaoResponse,
    OcupacaoDepartamentoResponse,
)
from app.services.relatorio_service import (
    relatorio_disciplinas_mais_procuradas,
    relatorio_taxa_reprovacao,
    relatorio_ocupacao_departamentos,
)

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get("/disciplinas-mais-procuradas", response_model=List[DisciplinaMaisProcuradaResponse])
def relatorio_procuradas(
    semestre: Optional[str] = Query(None, description="Filtrar por semestre letivo (ex: 2026.1)"),
    db: Session = Depends(get_db)
):
    """
    Relatório: Disciplinas mais procuradas no semestre.
    Ordenadas pelo total de solicitações de matrícula em ordem decrescente.
    """
    return relatorio_disciplinas_mais_procuradas(db, semestre)


@router.get("/taxa-reprovacao", response_model=List[TaxaReprovacaoResponse])
def relatorio_reprovacao(
    semestre: Optional[str] = Query(None, description="Filtrar por semestre letivo (opcional)"),
    db: Session = Depends(get_db)
):
    """
    Relatório: Taxa de reprovação por disciplina no histórico.
    Calculada como: (reprovações / total_avaliados) * 100%.
    """
    return relatorio_taxa_reprovacao(db, semestre)


@router.get("/ocupacao-departamentos", response_model=List[OcupacaoDepartamentoResponse])
def relatorio_ocupacao(
    semestre: Optional[str] = Query(None, description="Filtrar por semestre letivo (opcional)"),
    db: Session = Depends(get_db)
):
    """
    Relatório: Ocupação das turmas agrupadas por departamento.
    Apresenta vagas totais, vagas ocupadas, taxa percentual geral e turmas detalhadas.
    """
    return relatorio_ocupacao_departamentos(db, semestre)
