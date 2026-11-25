from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, field_validator
from app.config import EstadoTarifa


class TarifaCreate(BaseModel):
    conta_id: int
    tipo: str
    valor: Decimal
    estado: EstadoTarifa = EstadoTarifa.COBRADA

    @field_validator("valor")
    @classmethod
    def validar_valor(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.00"):
            raise ValueError("Valor da tarifa não pode ser negativo.")
        return v


class TarifaResponse(BaseModel):
    id: int
    conta_id: int
    tipo: str
    valor: Decimal
    data: datetime
    estado: EstadoTarifa

    model_config = ConfigDict(from_attributes=True)


class CobrancaMensalResponse(BaseModel):
    contas_processadas: int
    total_cobrado: Decimal
    mensagem: str
