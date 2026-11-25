from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator
from app.config import EstadoCartao


class CartaoBase(BaseModel):
    numero: str
    limite: Decimal = Decimal("1000.00")

    @field_validator("limite")
    @classmethod
    def validar_limite(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("O limite do cartão não pode ser negativo.")
        return round(v, 2)

    @field_validator("numero")
    @classmethod
    def validar_numero(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("O número do cartão não pode ser vazio.")
        return clean


class CartaoCreate(CartaoBase):
    conta_id: int


class CartaoUpdate(BaseModel):
    limite: Optional[Decimal] = None
    estado: Optional[EstadoCartao] = None

    @field_validator("limite")
    @classmethod
    def validar_limite(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < Decimal("0.00"):
            raise ValueError("O limite do cartão não pode ser negativo.")
        return round(v, 2) if v is not None else None


class CartaoResponse(CartaoBase):
    id: int
    conta_id: int
    estado: EstadoCartao
    data_criacao: datetime

    model_config = ConfigDict(from_attributes=True)
