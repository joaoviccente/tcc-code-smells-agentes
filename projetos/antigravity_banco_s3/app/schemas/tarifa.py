from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.config import TipoTarifa, EstadoTarifa


class TarifaBase(BaseModel):
    tipo: TipoTarifa
    valor: Decimal = Field(..., ge=0)
    estado: EstadoTarifa = Field(default=EstadoTarifa.PENDENTE)


class TarifaCreate(TarifaBase):
    conta_id: int


class TarifaCobrarMensalidadeRequest(BaseModel):
    debitar_saldo: bool = Field(default=True, description="Se True, debita imediatamente da conta se houver saldo+limite")


class TarifaResponse(TarifaBase):
    id: int
    conta_id: int
    data: datetime

    model_config = ConfigDict(from_attributes=True)
