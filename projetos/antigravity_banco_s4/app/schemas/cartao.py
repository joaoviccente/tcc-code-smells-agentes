from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.models.enums import EstadoCartao


class CartaoBase(BaseModel):
    numero: str = Field(..., min_length=4, max_length=20, description="Número do cartão")
    limite: Decimal = Field(default=Decimal("0.00"), ge=0, description="Limite de crédito do cartão")


class CartaoCreate(CartaoBase):
    conta_id: int = Field(..., description="ID da conta à qual o cartão pertence")


class CartaoUpdate(BaseModel):
    limite: Optional[Decimal] = Field(None, ge=0)
    estado: Optional[EstadoCartao] = None


class CartaoResponse(BaseModel):
    id: int
    conta_id: int
    numero: str
    limite: Decimal
    estado: EstadoCartao
    data_criacao: datetime

    model_config = ConfigDict(from_attributes=True)
