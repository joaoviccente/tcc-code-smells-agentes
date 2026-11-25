from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from app.models.enums import EstadoTurma
from app.schemas.disciplina import DisciplinaSimple

class TurmaBase(BaseModel):
    disciplina_id: int = Field(..., description="ID da disciplina ofertada")
    semestre: str = Field(..., min_length=4, max_length=20, description="Semestre letivo (ex: 2026.1)")
    professor: str = Field(..., min_length=2, max_length=120, description="Nome do professor")
    numero_vagas: int = Field(..., gt=0, description="Número total de vagas")
    horario: str = Field(..., min_length=3, max_length=150, description="Horário (ex: 'SEG 08:00-10:00, QUA 08:00-10:00')")
    estado: EstadoTurma = Field(default=EstadoTurma.ABERTA, description="Estado: aberta, lotada, cancelada, encerrada")

class TurmaCreate(TurmaBase):
    pass

class TurmaUpdate(BaseModel):
    disciplina_id: Optional[int] = None
    semestre: Optional[str] = Field(None, min_length=4, max_length=20)
    professor: Optional[str] = Field(None, min_length=2, max_length=120)
    numero_vagas: Optional[int] = Field(None, gt=0)
    horario: Optional[str] = Field(None, min_length=3, max_length=150)
    estado: Optional[EstadoTurma] = None

class TurmaResponse(TurmaBase):
    id: int
    vagas_ocupadas: int = 0
    vagas_restantes: int = 0
    disciplina: Optional[DisciplinaSimple] = None

    model_config = ConfigDict(from_attributes=True)
