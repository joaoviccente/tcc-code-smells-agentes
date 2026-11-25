from pydantic import BaseModel, ConfigDict
from typing import List, Optional

class DisciplinaProcuradaItem(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    departamento: str
    total_solicitacoes: int
    total_confirmadas: int
    total_fila_espera: int

    model_config = ConfigDict(from_attributes=True)

class RelatorioDisciplinasProcuradas(BaseModel):
    semestre: Optional[str] = None
    disciplinas: List[DisciplinaProcuradaItem]

class TaxaReprovacaoItem(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    departamento: str
    total_registros: int
    aprovados: int
    reprovados: int
    trancados: int
    taxa_reprovacao_percentual: float

    model_config = ConfigDict(from_attributes=True)

class RelatorioTaxaReprovacao(BaseModel):
    disciplinas: List[TaxaReprovacaoItem]

class TurmaOcupacaoItem(BaseModel):
    turma_id: int
    disciplina_codigo: str
    disciplina_nome: str
    professor: str
    horario: str
    numero_vagas: int
    vagas_ocupadas: int
    taxa_ocupacao_percentual: float
    estado: str

class DepartamentoOcupacaoItem(BaseModel):
    departamento: str
    total_turmas: int
    total_vagas_ofertadas: int
    total_vagas_ocupadas: int
    taxa_ocupacao_geral_percentual: float
    turmas: List[TurmaOcupacaoItem]

class RelatorioOcupacaoDepartamentos(BaseModel):
    semestre: Optional[str] = None
    departamentos: List[DepartamentoOcupacaoItem]
