from typing import List, Optional
from pydantic import BaseModel


class DisciplinaProcuradaItem(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    departamento: str
    total_solicitacoes: int


class RelatorioDisciplinasProcuradasResponse(BaseModel):
    semestre: Optional[str] = None
    disciplinas: List[DisciplinaProcuradaItem]


class TaxaReprovacaoItem(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    departamento: str
    total_concluidos: int
    total_aprovados: int
    total_reprovados: int
    taxa_reprovacao_percentual: float


class RelatorioTaxaReprovacaoResponse(BaseModel):
    disciplinas: List[TaxaReprovacaoItem]


class TurmaOcupacaoItem(BaseModel):
    turma_id: int
    disciplina_codigo: str
    disciplina_nome: str
    semestre: str
    vagas_totais: int
    vagas_ocupadas: int
    taxa_ocupacao_percentual: float


class DepartamentoOcupacaoItem(BaseModel):
    departamento: str
    total_turmas: int
    total_vagas: int
    vagas_ocupadas: int
    taxa_ocupacao_percentual: float
    turmas: List[TurmaOcupacaoItem]


class RelatorioOcupacaoDepartamentosResponse(BaseModel):
    semestre: Optional[str] = None
    departamentos: List[DepartamentoOcupacaoItem]
