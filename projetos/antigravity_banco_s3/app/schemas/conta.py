from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.config import TipoConta, EstadoConta


class ContaBase(BaseModel):
    numero: str = Field(..., min_length=3, max_length=20, description="Número único da conta")
    tipo: TipoConta = Field(default=TipoConta.CORRENTE, description="Tipo da conta: corrente ou poupanca")
    limite_credito: Decimal = Field(default=Decimal("0.00"), ge=0, description="Limite de crédito (cheque especial)")


class ContaCreate(ContaBase):
    cliente_id: int = Field(..., description="ID do cliente titular da conta")
    saldo_inicial: Decimal = Field(default=Decimal("0.00"), description="Saldo inicial da conta")


class ContaUpdate(BaseModel):
    tipo: Optional[TipoConta] = None
    limite_credito: Optional[Decimal] = Field(None, ge=0)
    estado: Optional[EstadoConta] = None


class ContaResponse(ContaBase):
    id: int
    cliente_id: int
    saldo: Decimal
    estado: EstadoConta
    saldo_negativo_desde: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
