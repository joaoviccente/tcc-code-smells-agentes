from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import EstadoTurma
from app.schemas.disciplina import DisciplinaSimple

class TurmaBase(BaseModel):
    disciplina_id: int
    semestre: str
    professor: str
    numero_vagas: int = Field(gt=0, description="Número de vagas deve ser maior que 0")
    horario: str = Field(description="Ex: SEG 08:00-10:00, QUA 08:00-10:00")
    estado: EstadoTurma = EstadoTurma.ABERTA

class TurmaCreate(TurmaBase):
    pass

class TurmaUpdate(BaseModel):
    disciplina_id: Optional[int] = None
    semestre: Optional[str] = None
    professor: Optional[str] = None
    numero_vagas: Optional[int] = Field(default=None, gt=0)
    horario: Optional[str] = None
    estado: Optional[EstadoTurma] = None

class TurmaResponse(BaseModel):
    id: int
    disciplina_id: int
    semestre: str
    professor: str
    numero_vagas: int
    horario: str
    estado: EstadoTurma
    vagas_ocupadas: int = 0
    vagas_disponiveis: int = 0
    disciplina: Optional[DisciplinaSimple] = None

    model_config = ConfigDict(from_attributes=True)
