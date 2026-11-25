from app.schemas.aluno import AlunoBase, AlunoCreate, AlunoUpdate, AlunoResponse
from app.schemas.disciplina import DisciplinaBase, DisciplinaCreate, DisciplinaUpdate, DisciplinaResponse, DisciplinaSimple
from app.schemas.turma import TurmaBase, TurmaCreate, TurmaUpdate, TurmaResponse
from app.schemas.matricula import MatriculaCreate, MatriculaAction, MatriculaResponse, FilaEsperaItem, FilaEsperaResponse
from app.schemas.historico import HistoricoBase, HistoricoCreate, HistoricoResponse
from app.schemas.relatorio import DisciplinaProcuraReport, TaxaReprovacaoReport, OcupacaoDepartamentoReport, OcupacaoTurmaItem

__all__ = [
    "AlunoBase",
    "AlunoCreate",
    "AlunoUpdate",
    "AlunoResponse",
    "DisciplinaBase",
    "DisciplinaCreate",
    "DisciplinaUpdate",
    "DisciplinaResponse",
    "DisciplinaSimple",
    "TurmaBase",
    "TurmaCreate",
    "TurmaUpdate",
    "TurmaResponse",
    "MatriculaCreate",
    "MatriculaAction",
    "MatriculaResponse",
    "FilaEsperaItem",
    "FilaEsperaResponse",
    "HistoricoBase",
    "HistoricoCreate",
    "HistoricoResponse",
    "DisciplinaProcuraReport",
    "TaxaReprovacaoReport",
    "OcupacaoDepartamentoReport",
    "OcupacaoTurmaItem"
]
