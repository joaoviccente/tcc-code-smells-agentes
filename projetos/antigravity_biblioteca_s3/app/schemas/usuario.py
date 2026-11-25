from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.enums import CategoriaUsuario, SituacaoUsuario


class UsuarioBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255, description="Nome completo do usuário")
    email: EmailStr = Field(..., description="E-mail único do usuário")
    matricula: str = Field(..., min_length=1, max_length=100, description="Matrícula única do usuário")
    categoria: CategoriaUsuario = Field(..., description="Categoria: aluno, professor ou visitante")


class UsuarioCreate(UsuarioBase):
    situacao: Optional[SituacaoUsuario] = Field(default=SituacaoUsuario.ATIVO, description="Situação cadastral")


class UsuarioUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    matricula: Optional[str] = Field(None, min_length=1, max_length=100)
    categoria: Optional[CategoriaUsuario] = None
    situacao: Optional[SituacaoUsuario] = None


class UsuarioResponse(UsuarioBase):
    id: int
    situacao: SituacaoUsuario
    data_suspensao_fim: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
