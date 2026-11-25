from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class PreRequisitoItem(BaseModel):
    id: int
    codigo: str
    nome: str

    model_config = ConfigDict(from_attributes=True)


class DisciplinaBase(BaseModel):
    codigo: str = Field(..., min_length=2, max_length=20, description="Código único da disciplina")
    nome: str = Field(..., min_length=2, max_length=150, description="Nome da disciplina")
    numero_creditos: int = Field(..., gt=0, le=32, description="Número de créditos da disciplina")
    carga_horaria: int = Field(..., gt=0, description="Carga horária total em horas")
    departamento: str = Field(..., min_length=2, max_length=100, description="Departamento responsável")


class DisciplinaCreate(DisciplinaBase):
    pass


class DisciplinaUpdate(BaseModel):
    codigo: Optional[str] = Field(None, min_length=2, max_length=20)
    nome: Optional[str] = Field(None, min_length=2, max_length=150)
    numero_creditos: Optional[int] = Field(None, gt=0, le=32)
    carga_horaria: Optional[int] = Field(None, gt=0)
    departamento: Optional[str] = Field(None, min_length=2, max_length=100)


class DisciplinaResponse(DisciplinaBase):
    id: int
    pre_requisitos: List[PreRequisitoItem] = []

    model_config = ConfigDict(from_attributes=True)


class PreRequisitoCreate(BaseModel):
    pre_requisito_id: int = Field(..., description="ID da disciplina que é pré-requisito")
