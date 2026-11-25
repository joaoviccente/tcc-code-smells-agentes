from typing import List, Optional
from pydantic import BaseModel

class DisciplinaProcuraReport(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    departamento: str
    total_solicitacoes: int
    total_confirmadas: int
    total_fila_espera: int

class TaxaReprovacaoReport(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    departamento: str
    total_avaliados: int
    total_aprovados: int
    total_reprovados: int
    taxa_reprovacao_percentual: float

class OcupacaoTurmaItem(BaseModel):
    turma_id: int
    disciplina_codigo: str
    disciplina_nome: str
    semestre: str
    professor: str
    numero_vagas: int
    confirmadas: int
    taxa_ocupacao_percentual: float

class OcupacaoDepartamentoReport(BaseModel):
    departamento: str
    total_turmas: int
    total_vagas: int
    total_confirmadas: int
    taxa_ocupacao_percentual: float
    turmas: List[OcupacaoTurmaItem] = []
