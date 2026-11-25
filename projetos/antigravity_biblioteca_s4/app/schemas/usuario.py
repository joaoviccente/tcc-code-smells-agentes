from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.enums import CategoriaUsuario, SituacaoUsuario


class UsuarioBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255, description="Nome do usuário")
    email: EmailStr = Field(..., description="E-mail do usuário")
    matricula: str = Field(..., min_length=1, max_length=100, description="Matrícula única")
    categoria: CategoriaUsuario = Field(..., description="aluno, professor ou visitante")


class UsuarioCreate(UsuarioBase):
    situacao: Optional[SituacaoUsuario] = Field(default=SituacaoUsuario.ATIVO, description="Situação inicial do usuário")


class UsuarioUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    matricula: Optional[str] = Field(None, min_length=1, max_length=100)
    categoria: Optional[CategoriaUsuario] = None
    situacao: Optional[SituacaoUsuario] = None
    data_fim_suspensao: Optional[datetime] = None


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: str
    matricula: str
    categoria: CategoriaUsuario
    situacao: SituacaoUsuario
    data_fim_suspensao: Optional[datetime] = None
