from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator
from app.config import TipoConta, EstadoConta


class ContaBase(BaseModel):
    numero: str
    tipo: TipoConta = TipoConta.CORRENTE
    limite_credito: Decimal = Decimal("0.00")

    @field_validator("limite_credito")
    @classmethod
    def validar_limite(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("O limite de crédito não pode ser negativo.")
        return round(v, 2)

    @field_validator("numero")
    @classmethod
    def validar_numero(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("O número da conta não pode ser vazio.")
        return clean


class ContaCreate(ContaBase):
    cliente_id: int


class ContaUpdate(BaseModel):
    tipo: Optional[TipoConta] = None
    limite_credito: Optional[Decimal] = None
    estado: Optional[EstadoConta] = None

    @field_validator("limite_credito")
    @classmethod
    def validar_limite(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < Decimal("0.00"):
            raise ValueError("O limite de crédito não pode ser negativo.")
        return round(v, 2) if v is not None else None


class ContaResponse(ContaBase):
    id: int
    cliente_id: int
    saldo: Decimal
    estado: EstadoConta
    data_saldo_negativo_inicio: Optional[datetime] = None
    data_criacao: datetime

    model_config = ConfigDict(from_attributes=True)
