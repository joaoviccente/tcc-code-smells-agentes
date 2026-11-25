from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.relatorio import (
    RelatorioDisciplinasProcuradasResponse,
    RelatorioTaxaReprovacaoResponse,
    RelatorioOcupacaoDepartamentosResponse,
    DisciplinaProcuradaItem,
    TaxaReprovacaoItem,
    DepartamentoOcupacaoItem,
    TurmaOcupacaoItem,
)
from app.services import relatorio_service

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get("/disciplinas-mais-procuradas", response_model=RelatorioDisciplinasProcuradasResponse)
def obter_disciplinas_mais_procuradas(
    semestre: Optional[str] = Query(None, description="Semestre letivo de consulta (ex: '2026.1')"),
    db: Session = Depends(get_db)
):
    """
    Relatório: disciplinas mais procuradas no semestre (ordenadas pelo total de solicitações).
    """
    dados = relatorio_service.relatorio_disciplinas_mais_procuradas(db, semestre=semestre)
    itens = [DisciplinaProcuradaItem(**d) for d in dados]
    return RelatorioDisciplinasProcuradasResponse(semestre=semestre, disciplinas=itens)


@router.get("/taxa-reprovacao", response_model=RelatorioTaxaReprovacaoResponse)
def obter_taxa_reprovacao(db: Session = Depends(get_db)):
    """
    Relatório: taxa de reprovação por disciplina no histórico acadêmico.
    Calcula percentual considerando reprovações e reprovações por falta sobre total de avaliados.
    """
    dados = relatorio_service.relatorio_taxa_reprovacao(db)
    itens = [TaxaReprovacaoItem(**d) for d in dados]
    return RelatorioTaxaReprovacaoResponse(disciplinas=itens)


@router.get("/ocupacao-departamentos", response_model=RelatorioOcupacaoDepartamentosResponse)
def obter_ocupacao_departamentos(
    semestre: Optional[str] = Query(None, description="Filtrar turmas pelo semestre letivo (ex: '2026.1')"),
    db: Session = Depends(get_db)
):
    """
    Relatório: ocupação das turmas agrupadas por departamento.
    Apresenta total de vagas oferecidas, vagas confirmadas e taxa de ocupação percentual.
    """
    dados = relatorio_service.relatorio_ocupacao_departamentos(db, semestre=semestre)
    deptos = []
    for d in dados:
        turmas_item = [TurmaOcupacaoItem(**t) for t in d["turmas"]]
        deptos.append(
            DepartamentoOcupacaoItem(
                departamento=d["departamento"],
                total_turmas=d["total_turmas"],
                total_vagas=d["total_vagas"],
                vagas_ocupadas=d["vagas_ocupadas"],
                taxa_ocupacao_percentual=d["taxa_ocupacao_percentual"],
                turmas=turmas_item,
            )
        )
    return RelatorioOcupacaoDepartamentosResponse(semestre=semestre, departamentos=deptos)
