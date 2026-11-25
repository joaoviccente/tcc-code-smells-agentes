from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

class DisciplinaSimple(BaseModel):
    id: int
    codigo: str
    nome: str
    numero_creditos: int
    carga_horaria: int
    departamento: str

    model_config = ConfigDict(from_attributes=True)

class DisciplinaBase(BaseModel):
    codigo: str
    nome: str
    numero_creditos: int = Field(gt=0, description="Número de créditos deve ser maior que 0")
    carga_horaria: int = Field(gt=0, description="Carga horária deve ser maior que 0")
    departamento: str

class DisciplinaCreate(DisciplinaBase):
    pre_requisito_ids: List[int] = Field(default_factory=list)

class DisciplinaUpdate(BaseModel):
    codigo: Optional[str] = None
    nome: Optional[str] = None
    numero_creditos: Optional[int] = Field(default=None, gt=0)
    carga_horaria: Optional[int] = Field(default=None, gt=0)
    departamento: Optional[str] = None
    pre_requisito_ids: Optional[List[int]] = None

class DisciplinaResponse(DisciplinaBase):
    id: int
    pre_requisitos: List[DisciplinaSimple] = []

    model_config = ConfigDict(from_attributes=True)
