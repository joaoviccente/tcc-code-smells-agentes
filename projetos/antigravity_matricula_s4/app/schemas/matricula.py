from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.config import EstadoMatricula, CategoriaAluno


class MatriculaSolicitarRequest(BaseModel):
    aluno_id: int = Field(..., description="ID do aluno")
    turma_id: int = Field(..., description="ID da turma desejada")


class MatriculaAcaoRequest(BaseModel):
    data_acao: Optional[datetime] = Field(
        None,
        description="Data/hora simulada para a ação (opcional, default é o momento atual UTC)"
    )


class MatriculaResponse(BaseModel):
    id: int
    aluno_id: int
    turma_id: int
    data: datetime
    estado: EstadoMatricula
    data_oferta_vaga: Optional[datetime] = None
    
    # Informações enriquecidas opcionais
    aluno_nome: Optional[str] = None
    aluno_categoria: Optional[CategoriaAluno] = None
    disciplina_codigo: Optional[str] = None
    disciplina_nome: Optional[str] = None
    semestre: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FilaEsperaItemResponse(BaseModel):
    posicao: int
    matricula_id: int
    aluno_id: int
    aluno_nome: str
    aluno_categoria: CategoriaAluno
    data_solicitacao: datetime
    estado: EstadoMatricula
    data_oferta_vaga: Optional[datetime] = None
    prazo_limite_confirmacao: Optional[datetime] = None
    horas_restantes: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class FilaEsperaResponse(BaseModel):
    turma_id: int
    disciplina_codigo: str
    disciplina_nome: str
    semestre: str
    total_na_fila: int
    vagas_totais: int
    vagas_ocupadas: int
    fila: list[FilaEsperaItemResponse]
