from datetime import datetime
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict
from app.models.enums import EstadoMulta


class MultaResponse(BaseModel):
    id: int
    emprestimo_id: int
    valor: Decimal
    estado: EstadoMulta
    data_geracao: datetime
    data_pagamento: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
