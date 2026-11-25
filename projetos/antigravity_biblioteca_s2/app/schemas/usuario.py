from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.enums import CategoriaUsuario, SituacaoUsuario


class UsuarioBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=150, description="Nome completo do usuário")
    email: EmailStr = Field(..., description="E-mail válido e único")
    matricula: str = Field(..., min_length=1, max_length=50, description="Matrícula única")
    categoria: CategoriaUsuario = Field(..., description="aluno, professor ou visitante")


class UsuarioCreate(UsuarioBase):
    pass


class UsuarioUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=1, max_length=150)
    email: Optional[EmailStr] = None
    matricula: Optional[str] = Field(None, min_length=1, max_length=50)
    categoria: Optional[CategoriaUsuario] = None
    situacao: Optional[SituacaoUsuario] = None
    data_fim_suspensao: Optional[datetime] = None


class UsuarioResponse(BaseModel):
    id: int
    nome: str
    email: str
    matricula: str
    categoria: CategoriaUsuario
    situacao: SituacaoUsuario
    data_fim_suspensao: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
