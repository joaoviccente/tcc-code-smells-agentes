import re
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

    @field_validator("mes_referencia")
    @classmethod
    def validar_mes_referencia(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}$", v):
            raise ValueError("Mês de referência deve estar no formato AAAA-MM (ex: 2026-11).")
        return v

    @field_validator("valor")
    @classmethod
    def validar_valor(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("Valor da fatura deve ser maior que zero.")
        return v


class FaturaPagamentoCreate(BaseModel):
    valor: Optional[Decimal] = None
    data_pagamento: Optional[datetime] = None

    @field_validator("valor")
    @classmethod
    def validar_valor(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= Decimal("0.00"):
            raise ValueError("Valor pago deve ser maior que zero.")
        return v


class FaturaResponse(BaseModel):
    id: int
    cartao_id: int
    mes_referencia: str
    valor: Decimal
    valor_original: Decimal
    data_vencimento: date
    data_pagamento: Optional[datetime] = None
    estado: EstadoFatura
    dias_atraso: int
    juros_acumulados: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcessarAtrasosResponse(BaseModel):
    faturas_atualizadas: int
    cartoes_bloqueados: int
    mensagem: str
