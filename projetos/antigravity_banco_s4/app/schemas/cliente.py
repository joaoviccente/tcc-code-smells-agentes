from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional
from app.models.enums import CategoriaCliente, SituacaoCliente
from app.utils.validators import validate_cpf


class ClienteBase(BaseModel):
    nome: str = Field(..., min_length=2, max_length=150, description="Nome completo do cliente")
    cpf: str = Field(..., description="CPF válido do cliente (apenas números ou formatado)")
    email: EmailStr = Field(..., description="E-mail válido do cliente")
    categoria: CategoriaCliente = Field(default=CategoriaCliente.COMUM, description="Categoria do cliente")

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, v: str) -> str:
        return validate_cpf(v)


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=2, max_length=150)
    email: Optional[EmailStr] = None
    categoria: Optional[CategoriaCliente] = None
    situacao: Optional[SituacaoCliente] = None


class ClienteResponse(BaseModel):
    id: int
    nome: str
    cpf: str
    email: str
    categoria: CategoriaCliente
    situacao: SituacaoCliente
    data_criacao: datetime

    model_config = ConfigDict(from_attributes=True)
