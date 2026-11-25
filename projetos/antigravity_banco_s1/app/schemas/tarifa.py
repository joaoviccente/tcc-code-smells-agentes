from decimal import Decimal
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.tarifa import EstadoTarifa


class TarifaBase(BaseModel):
    tipo: str = Field(..., max_length=50, description="Tipo da tarifa (ex: mensalidade, transferencia)")
    valor: Decimal = Field(..., ge=0, description="Valor da tarifa")
    descricao: Optional[str] = Field(None, max_length=255)


class TarifaCreate(TarifaBase):
    pass


class TarifaResponse(TarifaBase):
    id: int
    conta_id: int
    estado: EstadoTarifa
    data: datetime

    model_config = ConfigDict(from_attributes=True)
