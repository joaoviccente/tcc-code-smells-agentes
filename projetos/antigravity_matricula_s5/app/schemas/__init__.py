from app.schemas.aluno import AlunoBase, AlunoCreate, AlunoUpdate, AlunoResponse
from app.schemas.disciplina import (
    DisciplinaSimple,
    DisciplinaBase,
    DisciplinaCreate,
    DisciplinaUpdate,
    DisciplinaResponse,
)
from app.schemas.turma import TurmaBase, TurmaCreate, TurmaUpdate, TurmaResponse
from app.schemas.matricula import (
    MatriculaSolicitacao,
    MatriculaActionRequest,
    MatriculaResponse,
    MatriculaDetailResponse,
    WaitlistEntryResponse,
    FilaEsperaResponse,
)
from app.schemas.historico import HistoricoBase, HistoricoCreate, HistoricoResponse
from app.schemas.relatorio import (
    DisciplinaProcuradaItem,
    RelatorioDisciplinasProcuradas,
    TaxaReprovacaoItem,
    RelatorioTaxaReprovacao,
    TurmaOcupacaoItem,
    DepartamentoOcupacaoItem,
    RelatorioOcupacaoDepartamentos,
)

__all__ = [
    "AlunoBase",
    "AlunoCreate",
    "AlunoUpdate",
    "AlunoResponse",
    "DisciplinaSimple",
    "DisciplinaBase",
    "DisciplinaCreate",
    "DisciplinaUpdate",
    "DisciplinaResponse",
    "TurmaBase",
    "TurmaCreate",
    "TurmaUpdate",
    "TurmaResponse",
    "MatriculaSolicitacao",
    "MatriculaActionRequest",
    "MatriculaResponse",
    "MatriculaDetailResponse",
    "WaitlistEntryResponse",
    "FilaEsperaResponse",
    "HistoricoBase",
    "HistoricoCreate",
    "HistoricoResponse",
    "DisciplinaProcuradaItem",
    "RelatorioDisciplinasProcuradas",
    "TaxaReprovacaoItem",
    "RelatorioTaxaReprovacao",
    "TurmaOcupacaoItem",
    "DepartamentoOcupacaoItem",
    "RelatorioOcupacaoDepartamentos",
]
