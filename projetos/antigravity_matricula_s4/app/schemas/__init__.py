from app.schemas.aluno import AlunoCreate, AlunoUpdate, AlunoResponse
from app.schemas.disciplina import (
    DisciplinaCreate,
    DisciplinaUpdate,
    DisciplinaResponse,
    PreRequisitoCreate,
    PreRequisitoItem,
)
from app.schemas.turma import TurmaCreate, TurmaUpdate, TurmaResponse
from app.schemas.matricula import (
    MatriculaSolicitarRequest,
    MatriculaAcaoRequest,
    MatriculaResponse,
    FilaEsperaResponse,
    FilaEsperaItemResponse,
)
from app.schemas.historico import HistoricoCreate, HistoricoResponse
from app.schemas.relatorio import (
    RelatorioDisciplinasProcuradasResponse,
    RelatorioTaxaReprovacaoResponse,
    RelatorioOcupacaoDepartamentosResponse,
)

__all__ = [
    "AlunoCreate",
    "AlunoUpdate",
    "AlunoResponse",
    "DisciplinaCreate",
    "DisciplinaUpdate",
    "DisciplinaResponse",
    "PreRequisitoCreate",
    "PreRequisitoItem",
    "TurmaCreate",
    "TurmaUpdate",
    "TurmaResponse",
    "MatriculaSolicitarRequest",
    "MatriculaAcaoRequest",
    "MatriculaResponse",
    "FilaEsperaResponse",
    "FilaEsperaItemResponse",
    "HistoricoCreate",
    "HistoricoResponse",
    "RelatorioDisciplinasProcuradasResponse",
    "RelatorioTaxaReprovacaoResponse",
    "RelatorioOcupacaoDepartamentosResponse",
]
