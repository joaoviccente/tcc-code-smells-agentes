from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.config import EstadoTurma
from app.services.schedule_parser import parse_schedule


class TurmaBase(BaseModel):
    disciplina_id: int = Field(..., description="ID da disciplina")
    semestre: str = Field(..., min_length=4, max_length=20, description="Semestre letivo (ex: '2026.1')")
    professor: str = Field(..., min_length=2, max_length=150, description="Nome do professor responsável")
    numero_vagas: int = Field(..., gt=0, description="Capacidade máxima de vagas na turma")
    horario: str = Field(
        ...,
        description="Horário das aulas (ex: 'SEG 08:00-10:00, QUA 08:00-10:00')"
    )
    estado: EstadoTurma = Field(default=EstadoTurma.ABERTA, description="Estado da turma: aberta, lotada, cancelada, encerrada")

    @field_validator("horario")
    @classmethod
    def validate_horario(cls, v: str) -> str:
        try:
            parse_schedule(v)
        except ValueError as e:
            raise ValueError(str(e))
        return v.strip()


class TurmaCreate(TurmaBase):
    pass


class TurmaUpdate(BaseModel):
    disciplina_id: Optional[int] = None
    semestre: Optional[str] = Field(None, min_length=4, max_length=20)
    professor: Optional[str] = Field(None, min_length=2, max_length=150)
    numero_vagas: Optional[int] = Field(None, gt=0)
    horario: Optional[str] = None
    estado: Optional[EstadoTurma] = None

    @field_validator("horario")
    @classmethod
    def validate_horario(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                parse_schedule(v)
            except ValueError as e:
                raise ValueError(str(e))
            return v.strip()
        return v


class DisciplinaSimples(BaseModel):
    id: int
    codigo: str
    nome: str
    numero_creditos: int
    departamento: str

    model_config = ConfigDict(from_attributes=True)


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
    disciplina: Optional[DisciplinaSimples] = None

    model_config = ConfigDict(from_attributes=True)
