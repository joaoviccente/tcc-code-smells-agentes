from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.models.enums import EstadoReserva


class ReservaCreate(BaseModel):
    livro_id: int = Field(..., description="ID do livro a ser reservado")
    usuario_id: int = Field(..., description="ID do usuário solicitante da reserva")
    data: Optional[datetime] = Field(default=None, description="Data da reserva (opcional, padrão: data/hora atual)")


class ReservaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    livro_id: int
    usuario_id: int
    data: datetime
    posicao_na_fila: Optional[int] = None
    estado: EstadoReserva
    data_limite_retirada: Optional[datetime] = None
    exemplar_id: Optional[int] = None
