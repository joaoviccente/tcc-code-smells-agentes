from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator
from app.config import EstadoFatura


class FaturaCreate(BaseModel):
    cartao_id: int
    mes_referencia: str
    valor: Decimal
    data_vencimento: date

    @field_validator("valor")
    @classmethod
    def validar_valor(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("O valor da fatura deve ser maior que zero.")
        return round(v, 2)

    @field_validator("mes_referencia")
    @classmethod
    def validar_mes(cls, v: str) -> str:
        clean = v.strip()
        parts = clean.split("-")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit() or len(parts[0]) != 4 or len(parts[1]) != 2:
            raise ValueError("O mês de referência deve estar no formato AAAA-MM (ex: 2026-11).")
        return clean


class FaturaPagamentoRequest(BaseModel):
    valor_pago: Optional[Decimal] = None
    conta_origem_id: Optional[int] = None  # Se informado, debita da conta

    @field_validator("valor_pago")
    @classmethod
    def validar_valor(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= Decimal("0.00"):
            raise ValueError("O valor do pagamento deve ser maior que zero.")
        return round(v, 2) if v is not None else None


class FaturaResponse(BaseModel):
    id: int
    cartao_id: int
    mes_referencia: str
    valor: Decimal
    data_vencimento: date
    data_pagamento: Optional[datetime] = None
    valor_pago: Optional[Decimal] = None
    juros_acumulados: Decimal
    valor_total_atual: Decimal
    dias_atraso: int
    estado: EstadoFatura

    model_config = ConfigDict(from_attributes=True)
