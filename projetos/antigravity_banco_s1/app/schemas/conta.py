from decimal import Decimal
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.conta import EstadoConta, TipoConta


class ContaBase(BaseModel):
    tipo: TipoConta = Field(default=TipoConta.CORRENTE, description="Tipo da conta")
    limite_credito: Decimal = Field(default=Decimal("0.00"), ge=0, description="Limite de crédito concedido")


class ContaCreate(ContaBase):
    cliente_id: int = Field(..., description="ID do cliente titular")
    numero: str = Field(..., min_length=3, max_length=30, description="Número único da conta")


class ContaUpdate(BaseModel):
    tipo: Optional[TipoConta] = None
    limite_credito: Optional[Decimal] = Field(None, ge=0)
    estado: Optional[EstadoConta] = None


class ContaResponse(ContaBase):
    id: int
    cliente_id: int
    numero: str
    saldo: Decimal
    estado: EstadoConta
    data_saldo_negativo: Optional[datetime] = None
    data_criacao: datetime

    model_config = ConfigDict(from_attributes=True)


class EncerramentoContaResponse(BaseModel):
    mensagem: str
    conta: ContaResponse
    cartoes_cancelados: int
