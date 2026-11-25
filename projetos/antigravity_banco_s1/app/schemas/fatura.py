from decimal import Decimal
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.fatura import EstadoFatura


class FaturaBase(BaseModel):
    mes_referencia: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="Mês de referência formato YYYY-MM")
    valor: Decimal = Field(..., ge=0, description="Valor da fatura")
    data_vencimento: date = Field(..., description="Data de vencimento da fatura")


class FaturaCreate(FaturaBase):
    pass


class FaturaPagamento(BaseModel):
    valor_pago: Optional[Decimal] = Field(None, gt=0, description="Valor a pagar. Se omitido, quita o valor total com juros.")
    conta_id: Optional[int] = Field(None, description="ID da conta para débito automático do pagamento (opcional)")


class FaturaResponse(FaturaBase):
    id: int
    cartao_id: int
    valor_pago: Decimal
    juros_acumulados: Decimal
    valor_total_devido: Decimal
    data_pagamento: Optional[datetime] = None
    estado: EstadoFatura
    data_criacao: datetime

    model_config = ConfigDict(from_attributes=True)
