from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.models.enums import EstadoTurma


class TurmaBase(BaseModel):
    disciplina_id: int = Field(..., description="ID da disciplina à qual a turma pertence")
    semestre: str = Field(..., min_length=1, max_length=20, description="Semestre letivo (ex: 2026.1)")
    professor: str = Field(..., min_length=1, max_length=150, description="Nome do professor")
    numero_vagas: int = Field(..., ge=0, description="Número total de vagas na turma (>= 0)")
    horario: str = Field(..., min_length=1, max_length=100, description="Horário das aulas (ex: SEG 08:00-10:00, QUA 08:00-10:00)")
    estado: EstadoTurma = Field(default=EstadoTurma.ABERTA, description="Estado: aberta, lotada, cancelada, encerrada")


class TurmaCreate(TurmaBase):
    pass


class TurmaUpdate(BaseModel):
    disciplina_id: Optional[int] = None
    semestre: Optional[str] = Field(None, min_length=1, max_length=20)
    professor: Optional[str] = Field(None, min_length=1, max_length=150)
    numero_vagas: Optional[int] = Field(None, ge=0)
    horario: Optional[str] = Field(None, min_length=1, max_length=100)
    estado: Optional[EstadoTurma] = None


class TurmaResponse(TurmaBase):
    id: int
    disciplina_codigo: Optional[str] = None
    disciplina_nome: Optional[str] = None
    vagas_ocupadas: int = 0
    vagas_disponiveis: int = 0
    total_espera: int = 0

    model_config = ConfigDict(from_attributes=True)
