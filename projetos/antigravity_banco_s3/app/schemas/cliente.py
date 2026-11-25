from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from app.config import CategoriaCliente, SituacaoCliente
from app.utils.validators import validate_cpf, clean_cpf, format_cpf


class ClienteBase(BaseModel):
    nome: str = Field(..., min_length=2, max_length=150, description="Nome completo do cliente")
    email: EmailStr = Field(..., description="E-mail único do cliente")
    categoria: CategoriaCliente = Field(default=CategoriaCliente.COMUM, description="Categoria do cliente")
    situacao: SituacaoCliente = Field(default=SituacaoCliente.ATIVO, description="Situação cadastral do cliente")


class ClienteCreate(ClienteBase):
    cpf: str = Field(..., description="CPF válido do cliente (apenas dígitos ou com pontuação)")

    @field_validator("cpf")
    @classmethod
    def check_cpf(cls, v: str) -> str:
        digits = clean_cpf(v)
        if not validate_cpf(digits):
            raise ValueError("CPF inválido.")
        return format_cpf(digits)


class ClienteUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=2, max_length=150)
    email: Optional[EmailStr] = None
    categoria: Optional[CategoriaCliente] = None
    situacao: Optional[SituacaoCliente] = None


class ClienteResponse(ClienteBase):
    id: int
    cpf: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
