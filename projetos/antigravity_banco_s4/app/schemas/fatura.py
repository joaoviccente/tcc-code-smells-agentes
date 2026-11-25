from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
import re
from app.models.enums import EstadoFatura


class FaturaCreate(BaseModel):
    cartao_id: int = Field(..., description="ID do cartão associado à fatura")
    mes_referencia: str = Field(..., description="Mês de referência no formato AAAA-MM (ex: 2026-11)")
    valor: Decimal = Field(default=Decimal("0.00"), ge=0, description="Valor inicial da fatura")
    data_vencimento: date = Field(..., description="Data de vencimento da fatura")

    @field_validator("mes_referencia")
    @classmethod
    def validar_mes_referencia(cls, v: str) -> str:
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", v):
            raise ValueError("Mês de referência deve estar no formato AAAA-MM (ex: 2026-11)")
        return v


class FaturaPagamentoRequest(BaseModel):
    valor: Decimal = Field(..., gt=0, description="Valor pago para abatimento da fatura")


class FaturaResponse(BaseModel):
    id: int
    cartao_id: int
    mes_referencia: str
    valor: Decimal
    valor_pago: Decimal
    data_vencimento: date
    estado: EstadoFatura
    juros_acumulados: Decimal
    data_pagamento: Optional[datetime] = None
    valor_total_devido: Decimal

    model_config = ConfigDict(from_attributes=True)
