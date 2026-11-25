from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator
from app.config import TipoConta, EstadoConta


class ContaBase(BaseModel):
    cliente_id: int
    numero: str
    tipo: TipoConta = TipoConta.CORRENTE
    saldo: Decimal = Decimal("0.00")
    limite_credito: Decimal = Decimal("0.00")
    estado: EstadoConta = EstadoConta.ATIVA

    @field_validator("numero")
    @classmethod
    def validar_numero(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Número da conta não pode ser vazio.")
        return v

    @field_validator("limite_credito")
    @classmethod
    def validar_limite(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("Limite de crédito não pode ser negativo.")
        return v


class ContaCreate(ContaBase):
    pass


class ContaUpdate(BaseModel):
    tipo: Optional[TipoConta] = None
    limite_credito: Optional[Decimal] = None
    estado: Optional[EstadoConta] = None

    @field_validator("limite_credito")
    @classmethod
    def validar_limite(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < Decimal("0.00"):
            raise ValueError("Limite de crédito não pode ser negativo.")
        return v


class ContaResponse(ContaBase):
    id: int
    data_saldo_negativo_desde: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContaEncerrarResponse(BaseModel):
    id: int
    numero: str
    estado: EstadoConta
    mensagem: str
