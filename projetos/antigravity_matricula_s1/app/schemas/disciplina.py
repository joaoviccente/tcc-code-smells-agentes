from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class PreRequisitoItem(BaseModel):
    id: int
    codigo: str
    nome: str

    model_config = ConfigDict(from_attributes=True)


class DisciplinaBase(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=20, description="Código da disciplina (ex: MAT001)")
    nome: str = Field(..., min_length=1, max_length=150, description="Nome da disciplina")
    numero_creditos: int = Field(..., gt=0, description="Número de créditos acadêmicos (> 0)")
    carga_horaria: int = Field(..., gt=0, description="Carga horária total em horas (> 0)")
    departamento: str = Field(..., min_length=1, max_length=100, description="Departamento responsável")


class DisciplinaCreate(DisciplinaBase):
    pass


class DisciplinaUpdate(BaseModel):
    codigo: Optional[str] = Field(None, min_length=1, max_length=20)
    nome: Optional[str] = Field(None, min_length=1, max_length=150)
    numero_creditos: Optional[int] = Field(None, gt=0)
    carga_horaria: Optional[int] = Field(None, gt=0)
    departamento: Optional[str] = Field(None, min_length=1, max_length=100)


class PreRequisitoCreate(BaseModel):
    prerequisito_id: int = Field(..., description="ID da disciplina exigida como pré-requisito")


class DisciplinaResponse(DisciplinaBase):
    id: int
    pre_requisitos: List[PreRequisitoItem] = []

    model_config = ConfigDict(from_attributes=True)
