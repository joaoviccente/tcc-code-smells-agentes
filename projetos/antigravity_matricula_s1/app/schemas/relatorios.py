from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class DisciplinaMaisProcuradaResponse(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    departamento: str
    total_solicitacoes: int
    total_confirmadas: int
    total_espera: int

    model_config = ConfigDict(from_attributes=True)


class TaxaReprovacaoResponse(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    departamento: str
    total_aprovados: int
    total_reprovados: int
    total_trancados: int
    total_avaliados: int  # aprovados + reprovados
    taxa_reprovacao_percentual: float

    model_config = ConfigDict(from_attributes=True)


class OcupacaoTurmaItem(BaseModel):
    turma_id: int
    disciplina_codigo: str
    disciplina_nome: str
    semestre: str
    professor: str
    horario: str
    estado: str
    vagas_totais: int
    vagas_ocupadas: int
    taxa_ocupacao_percentual: float

    model_config = ConfigDict(from_attributes=True)


class OcupacaoDepartamentoResponse(BaseModel):
    departamento: str
    vagas_totais: int
    vagas_ocupadas: int
    taxa_ocupacao_geral_percentual: float
    turmas: List[OcupacaoTurmaItem]

    model_config = ConfigDict(from_attributes=True)
