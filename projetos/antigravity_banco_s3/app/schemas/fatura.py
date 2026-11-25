from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.config import EstadoFatura


class FaturaBase(BaseModel):
    mes_referencia: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="Mês de referência formato AAAA-MM (ex: 2026-11)")
    valor: Decimal = Field(..., ge=0, description="Valor da fatura")
    data_vencimento: date = Field(..., description="Data de vencimento da fatura")


class FaturaCreate(FaturaBase):
    cartao_id: int = Field(..., description="ID do cartão de crédito")


class FaturaPagamentoRequest(BaseModel):
    valor_pago: Optional[Decimal] = Field(None, gt=0, description="Valor pago (se nulo, paga o total com juros)")
    debitar_da_conta: bool = Field(default=False, description="Se True, debita automaticamente o valor da conta vinculada ao cartão")


class FaturaResponse(FaturaBase):
    id: int
    cartao_id: int
    estado: EstadoFatura
    valor_pago: Decimal
    data_pagamento: Optional[datetime] = None
    juros_acumulados: Decimal
    valor_total: Decimal

    model_config = ConfigDict(from_attributes=True)
