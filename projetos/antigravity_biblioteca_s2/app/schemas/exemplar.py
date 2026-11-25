from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import EstadoExemplar


class ExemplarBase(BaseModel):
    livro_id: int = Field(..., gt=0, description="ID do livro ao qual pertence")
    codigo_tombo: str = Field(..., min_length=1, max_length=50, description="Código de tombo único")
    estado: Optional[EstadoExemplar] = Field(default=EstadoExemplar.DISPONIVEL)


class ExemplarCreate(ExemplarBase):
    pass


class ExemplarUpdate(BaseModel):
    codigo_tombo: Optional[str] = Field(None, min_length=1, max_length=50)
    estado: Optional[EstadoExemplar] = None


class ExemplarResponse(BaseModel):
    id: int
    livro_id: int
    codigo_tombo: str
    estado: EstadoExemplar

    model_config = ConfigDict(from_attributes=True)
