from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.config import EstadoMulta


class MultaResponse(BaseModel):
    id: int
    emprestimo_id: int
    valor: Decimal = Field(..., examples=[10.00])
    estado: EstadoMulta
    data_geracao: datetime
    data_pagamento: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PagamentoMultaResponse(BaseModel):
    mensagem: str
    multa: MultaResponse
