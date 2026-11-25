from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.models.enums import EstadoExemplar


class ExemplarBase(BaseModel):
    livro_id: int = Field(..., description="ID do livro ao qual o exemplar pertence")
    codigo_tombo: str = Field(..., min_length=1, max_length=100, description="Código de tombo único do exemplar")
    estado: Optional[EstadoExemplar] = Field(default=EstadoExemplar.DISPONIVEL, description="Estado do exemplar")


class ExemplarCreate(ExemplarBase):
    pass


class ExemplarUpdate(BaseModel):
    livro_id: Optional[int] = None
    codigo_tombo: Optional[str] = Field(None, min_length=1, max_length=100)
    estado: Optional[EstadoExemplar] = None


class ExemplarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    livro_id: int
    codigo_tombo: str
    estado: EstadoExemplar
