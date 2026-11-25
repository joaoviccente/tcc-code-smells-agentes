from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.relatorio import (
    RelatorioDisciplinasProcuradas,
    RelatorioTaxaReprovacao,
    RelatorioOcupacaoDepartamentos,
)
from app.services.relatorio_service import (
    get_disciplinas_mais_procuradas,
    get_taxa_reprovacao_por_disciplina,
    get_ocupacao_turmas_por_departamento,
)

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get("/disciplinas-mais-procuradas", response_model=RelatorioDisciplinasProcuradas)
def relatorio_disciplinas_mais_procuradas(
    semestre: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Relatório de disciplinas mais procuradas no semestre especificado
    (ou geral caso não informado).
    """
    return get_disciplinas_mais_procuradas(db, semestre=semestre)


@router.get("/taxa-reprovacao", response_model=RelatorioTaxaReprovacao)
def relatorio_taxa_reprovacao(db: Session = Depends(get_db)):
    """
    Relatório da taxa de reprovação por disciplina calculada a partir do histórico acadêmico.
    """
    return get_taxa_reprovacao_por_disciplina(db)


@router.get("/ocupacao-departamentos", response_model=RelatorioOcupacaoDepartamentos)
def relatorio_ocupacao_departamentos(
    semestre: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Relatório de taxa de ocupação das turmas agrupadas por departamento.
    """
    return get_ocupacao_turmas_por_departamento(db, semestre=semestre)
