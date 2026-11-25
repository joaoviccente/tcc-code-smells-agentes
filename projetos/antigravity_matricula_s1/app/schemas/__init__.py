from app.schemas.aluno import AlunoCreate, AlunoUpdate, AlunoResponse
from app.schemas.disciplina import (
    DisciplinaCreate,
    DisciplinaUpdate,
    DisciplinaResponse,
    PreRequisitoCreate,
)
from app.schemas.turma import TurmaCreate, TurmaUpdate, TurmaResponse
from app.schemas.matricula import (
    MatriculaSolicitar,
    MatriculaResponse,
    FilaEsperaItemResponse,
    MensagemRetorno,
)
from app.schemas.historico import HistoricoCreate, HistoricoUpdate, HistoricoResponse
from app.schemas.relatorios import (
    DisciplinaMaisProcuradaResponse,
    TaxaReprovacaoResponse,
    OcupacaoDepartamentoResponse,
    OcupacaoTurmaItem,
)

__all__ = [
    "AlunoCreate",
    "AlunoUpdate",
    "AlunoResponse",
    "DisciplinaCreate",
    "DisciplinaUpdate",
    "DisciplinaResponse",
    "PreRequisitoCreate",
    "TurmaCreate",
    "TurmaUpdate",
    "TurmaResponse",
    "MatriculaSolicitar",
    "MatriculaResponse",
    "FilaEsperaItemResponse",
    "MensagemRetorno",
    "HistoricoCreate",
    "HistoricoUpdate",
    "HistoricoResponse",
    "DisciplinaMaisProcuradaResponse",
    "TaxaReprovacaoResponse",
    "OcupacaoDepartamentoResponse",
    "OcupacaoTurmaItem",
]
