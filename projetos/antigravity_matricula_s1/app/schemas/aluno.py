from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.enums import CategoriaAluno, SituacaoAluno


class AlunoBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=150, description="Nome completo do aluno")
    matricula: str = Field(..., min_length=1, max_length=50, description="Número de matrícula único")
    email: EmailStr = Field(..., description="Endereço de e-mail institucional")
    categoria: CategoriaAluno = Field(..., description="Categoria: graduacao, pos ou especial")
    situacao: SituacaoAluno = Field(default=SituacaoAluno.ATIVO, description="Situação: ativo, trancado ou jubilado")


class AlunoCreate(AlunoBase):
    pass


class AlunoUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=1, max_length=150)
    matricula: Optional[str] = Field(None, min_length=1, max_length=50)
    email: Optional[EmailStr] = None
    categoria: Optional[CategoriaAluno] = None
    situacao: Optional[SituacaoAluno] = None


class AlunoResponse(AlunoBase):
    id: int
    max_creditos: Optional[int] = None
    limite_trancamentos: Optional[int] = None
    prazo_cancelamento_dias: Optional[int] = None
    prioridade_espera: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
