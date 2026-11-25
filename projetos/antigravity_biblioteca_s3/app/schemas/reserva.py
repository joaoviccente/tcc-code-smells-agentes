from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import EstadoReserva


class ReservaCreate(BaseModel):
    livro_id: int = Field(..., gt=0, description="ID do livro a ser reservado")
    usuario_id: int = Field(..., gt=0, description="ID do usuário")
    data: Optional[datetime] = Field(default=None, description="Data/hora da reserva (opcional, padrão atual)")


class ReservaResponse(BaseModel):
    id: int
    livro_id: int
    usuario_id: int
    exemplar_id: Optional[int] = None
    data: datetime
    posicao_fila: Optional[int] = None
    estado: EstadoReserva
    data_limite_retirada: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
