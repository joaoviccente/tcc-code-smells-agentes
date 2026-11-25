from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.config import CategoriaUsuario, SituacaoUsuario


class UsuarioBase(BaseModel):
    nome: str = Field(..., min_length=2, max_length=255, examples=["João Silva"])
    email: EmailStr = Field(..., examples=["joao@universidade.edu.br"])
    matricula: str = Field(..., min_length=1, max_length=50, examples=["2024001"])
    categoria: CategoriaUsuario = Field(..., examples=[CategoriaUsuario.ALUNO])


class UsuarioCreate(UsuarioBase):
    situacao: SituacaoUsuario = Field(default=SituacaoUsuario.ATIVO)


class UsuarioUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    matricula: str | None = Field(default=None, min_length=1, max_length=50)
    categoria: CategoriaUsuario | None = None
    situacao: SituacaoUsuario | None = None
    suspenso_ate: datetime | None = None


class UsuarioResponse(UsuarioBase):
    id: int
    situacao: SituacaoUsuario
    suspenso_ate: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
