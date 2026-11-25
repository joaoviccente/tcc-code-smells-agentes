from decimal import Decimal
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.cartao import EstadoCartao


class CartaoBase(BaseModel):
    limite: Decimal = Field(default=Decimal("0.00"), ge=0, description="Limite do cartão")


class CartaoCreate(CartaoBase):
    conta_id: int = Field(..., description="ID da conta vinculada ao cartão")
    numero: str = Field(..., min_length=4, max_length=30, description="Número identificador do cartão")


class CartaoUpdate(BaseModel):
    limite: Optional[Decimal] = Field(None, ge=0)
    estado: Optional[EstadoCartao] = None


class CartaoResponse(CartaoBase):
    id: int
    conta_id: int
    numero: str
    estado: EstadoCartao
    data_criacao: datetime

    model_config = ConfigDict(from_attributes=True)
