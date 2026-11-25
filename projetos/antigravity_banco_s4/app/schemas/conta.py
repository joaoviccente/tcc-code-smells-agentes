from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from app.models.enums import TipoConta, EstadoConta


class ContaBase(BaseModel):
    numero: str = Field(..., min_length=1, max_length=20, description="Número da conta")
    tipo: TipoConta = Field(default=TipoConta.CORRENTE, description="Tipo da conta")
    limite_de_credito: Decimal = Field(default=Decimal("0.00"), ge=0, description="Limite de crédito concedido à conta")


class ContaCreate(ContaBase):
    cliente_id: int = Field(..., description="ID do cliente titular da conta")
    saldo_inicial: Decimal = Field(default=Decimal("0.00"), ge=0, description="Saldo inicial para abertura da conta")


class ContaUpdate(BaseModel):
    tipo: Optional[TipoConta] = None
    limite_de_credito: Optional[Decimal] = Field(None, ge=0)
    estado: Optional[EstadoConta] = None


class ContaResponse(BaseModel):
    id: int
    cliente_id: int
    numero: str
    tipo: TipoConta
    saldo: Decimal
    limite_de_credito: Decimal
    estado: EstadoConta
    data_saldo_negativo_inicio: Optional[datetime] = None
    data_criacao: datetime

    model_config = ConfigDict(from_attributes=True)


class ContaEncerramentoResponse(BaseModel):
    mensagem: str
    conta_id: int
    estado: EstadoConta
    cartoes_cancelados_ids: List[int]
