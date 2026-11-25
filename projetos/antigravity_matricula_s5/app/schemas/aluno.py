from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime
from app.models.enums import CategoriaAluno, SituacaoAluno

class AlunoBase(BaseModel):
    nome: str = Field(..., min_length=2, max_length=120, description="Nome completo do aluno")
    matricula: str = Field(..., min_length=2, max_length=50, description="Número de matrícula único")
    e_mail: EmailStr = Field(..., description="E-mail institucional ou de contato")
    categoria: CategoriaAluno = Field(..., description="Categoria do aluno: graduacao, pos ou especial")
    situacao: SituacaoAluno = Field(default=SituacaoAluno.ATIVO, description="Situação: ativo, trancado ou jubilado")

class AlunoCreate(AlunoBase):
    pass

class AlunoUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=2, max_length=120)
    e_mail: Optional[EmailStr] = None
    categoria: Optional[CategoriaAluno] = None
    situacao: Optional[SituacaoAluno] = None

class AlunoResponse(AlunoBase):
    id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
