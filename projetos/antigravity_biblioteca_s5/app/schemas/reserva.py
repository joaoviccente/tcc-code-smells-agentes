from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.config import EstadoReserva


class ReservaCreate(BaseModel):
    usuario_id: int = Field(..., gt=0, examples=[1])
    livro_id: int = Field(..., gt=0, examples=[1])
    data_reserva: datetime | None = Field(
        default=None,
        description="Data da reserva opcional (padrão é agora)",
    )


class ReservaResponse(BaseModel):
    id: int
    livro_id: int
    usuario_id: int
    data_reserva: datetime
    posicao_fila: int
    estado: EstadoReserva
    data_disponibilizacao: datetime | None = None
    exemplar_id: int | None = None

    model_config = ConfigDict(from_attributes=True)
