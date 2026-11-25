from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List

class DisciplinaSimple(BaseModel):
    id: int
    codigo: str
    nome: str
    numero_creditos: int
    carga_horaria: int
    departamento: str

    model_config = ConfigDict(from_attributes=True)

class DisciplinaBase(BaseModel):
    codigo: str = Field(..., min_length=2, max_length=20, description="Código único da disciplina")
    nome: str = Field(..., min_length=2, max_length=150, description="Nome da disciplina")
    numero_creditos: int = Field(..., gt=0, description="Número de créditos acadêmicos")
    carga_horaria: int = Field(..., gt=0, description="Carga horária em horas")
    departamento: str = Field(..., min_length=2, max_length=100, description="Departamento responsável")

class DisciplinaCreate(DisciplinaBase):
    prerequisitos_ids: Optional[List[int]] = Field(default=[], description="Lista de IDs de disciplinas pré-requisito")

class DisciplinaUpdate(BaseModel):
    codigo: Optional[str] = Field(None, min_length=2, max_length=20)
    nome: Optional[str] = Field(None, min_length=2, max_length=150)
    numero_creditos: Optional[int] = Field(None, gt=0)
    carga_horaria: Optional[int] = Field(None, gt=0)
    departamento: Optional[str] = Field(None, min_length=2, max_length=100)
    prerequisitos_ids: Optional[List[int]] = None

class DisciplinaResponse(DisciplinaBase):
    id: int
    prerequisitos: List[DisciplinaSimple] = []

    model_config = ConfigDict(from_attributes=True)
