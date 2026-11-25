"""Schemas Pydantic para validação e serialização de Matrícula e Fila de Espera."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.models.enums import EstadoMatricula


class MatriculaSolicitar(BaseModel):
    aluno_id: int = Field(..., description="ID do aluno solicitante")
    turma_id: int = Field(..., description="ID da turma desejada")
    data: Optional[datetime] = Field(None, description="Data da solicitação (opcional, padrão: data/hora atual)")
    auto_confirm: Optional[bool] = Field(None, description="Se deve auto-confirmar caso haja vaga")


class MatriculaResponse(BaseModel):
    id: int
    aluno_id: int
    turma_id: int
    data: datetime
    data_limite_confirmacao: Optional[datetime] = None
    estado: EstadoMatricula
    aluno_nome: Optional[str] = None
    aluno_matricula: Optional[str] = None
    disciplina_codigo: Optional[str] = None
    disciplina_nome: Optional[str] = None
    turma_semestre: Optional[str] = None
    turma_horario: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FilaEsperaItemResponse(BaseModel):
    posicao: int
    matricula_id: int
    aluno_id: int
    aluno_nome: str
    aluno_categoria: str
    prioridade: str
    prioridade_num: int
    data_solicitacao: datetime
    data_limite_confirmacao: Optional[datetime] = None
    estado: str

    model_config = ConfigDict(from_attributes=True)


class MensagemRetorno(BaseModel):
    mensagem: str
    matricula: Optional[MatriculaResponse] = None
