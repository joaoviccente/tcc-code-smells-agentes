from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict
from app.models.enums import CategoriaAluno, SituacaoAluno

class AlunoBase(BaseModel):
    nome: str
    matricula: str
    email: EmailStr
    categoria: CategoriaAluno
    situacao: SituacaoAluno = SituacaoAluno.ATIVO

class AlunoCreate(AlunoBase):
    pass

class AlunoUpdate(BaseModel):
    nome: Optional[str] = None
    matricula: Optional[str] = None
    email: Optional[EmailStr] = None
    categoria: Optional[CategoriaAluno] = None
    situacao: Optional[SituacaoAluno] = None

class AlunoResponse(AlunoBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
