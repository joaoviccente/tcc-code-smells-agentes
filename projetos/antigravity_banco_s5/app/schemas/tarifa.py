from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, field_validator
from app.config import TipoTarifa, EstadoTarifa


class TarifaBase(BaseModel):
    conta_id: int
    tipo: TipoTarifa
    valor: Decimal
    estado: EstadoTarifa = EstadoTarifa.PENDENTE

    @field_validator("valor")
    @classmethod
    def validar_valor(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("O valor da tarifa não pode ser negativo.")
        return round(v, 2)


class TarifaCreate(TarifaBase):
    pass


class TarifaResponse(TarifaBase):
    id: int
    data: datetime

    model_config = ConfigDict(from_attributes=True)
