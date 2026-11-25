from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict
from app.models.enums import EstadoTarifa


class TarifaResponse(BaseModel):
    id: int
    conta_id: int
    tipo: str
    valor: Decimal
    data: datetime
    estado: EstadoTarifa

    model_config = ConfigDict(from_attributes=True)


class CobrarMensalidadeResponse(BaseModel):
    mensagem: str
    contas_processadas: int
    tarifas_cobradas: int
    valor_total_arrecadado: Decimal
