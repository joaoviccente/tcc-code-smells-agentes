from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator
from app.config import EstadoCartao


class CartaoBase(BaseModel):
    conta_id: int
    numero: str
    limite: Decimal = Decimal("0.00")
    estado: EstadoCartao = EstadoCartao.ATIVO

    @field_validator("numero")
    @classmethod
    def validar_numero(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Número do cartão não pode ser vazio.")
        return v

    @field_validator("limite")
    @classmethod
    def validar_limite(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("Limite do cartão não pode ser negativo.")
        return v


class CartaoCreate(CartaoBase):
    pass


class CartaoUpdate(BaseModel):
    limite: Optional[Decimal] = None
    estado: Optional[EstadoCartao] = None

    @field_validator("limite")
    @classmethod
    def validar_limite(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < Decimal("0.00"):
            raise ValueError("Limite do cartão não pode ser negativo.")
        return v


class CartaoResponse(CartaoBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
