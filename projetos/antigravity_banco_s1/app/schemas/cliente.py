from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.cliente import CategoriaCliente, SituacaoCliente
from app.schemas.common import CPF


class ClienteBase(BaseModel):
    nome: str = Field(..., min_length=2, max_length=120, description="Nome completo do cliente")
    email: EmailStr = Field(..., description="E-mail único do cliente")
    categoria: CategoriaCliente = Field(default=CategoriaCliente.COMUM, description="Categoria do cliente")
    situacao: SituacaoCliente = Field(default=SituacaoCliente.ATIVO, description="Situação cadastral")


class ClienteCreate(ClienteBase):
    cpf: CPF = Field(..., description="CPF válido com 11 dígitos")


class ClienteUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=2, max_length=120)
    email: Optional[EmailStr] = None
    categoria: Optional[CategoriaCliente] = None
    situacao: Optional[SituacaoCliente] = None


class ClienteResponse(ClienteBase):
    id: int
    cpf: str
    data_criacao: datetime

    model_config = ConfigDict(from_attributes=True)
