from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import EstadoReserva


class ReservaCreate(BaseModel):
    livro_id: int = Field(..., gt=0, description="ID do livro a ser reservado")
    usuario_id: int = Field(..., gt=0, description="ID do usuário que realiza a reserva")
    data: Optional[datetime] = Field(None, description="Data/hora da reserva (padrão: agora)")


class ReservaResponse(BaseModel):
    id: int
    livro_id: int
    usuario_id: int
    data: datetime
    posicao_fila: int
    estado: EstadoReserva
    data_disponibilizacao: Optional[datetime] = None
    data_limite_retirada: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
