from pydantic import BaseModel, ConfigDict, Field

from app.config import EstadoExemplar


class ExemplarBase(BaseModel):
    livro_id: int = Field(..., gt=0, examples=[1])
    codigo_tombo: str = Field(..., min_length=1, max_length=50, examples=["TMB-001"])


class ExemplarCreate(ExemplarBase):
    estado: EstadoExemplar = Field(default=EstadoExemplar.DISPONIVEL)


class ExemplarUpdate(BaseModel):
    livro_id: int | None = Field(default=None, gt=0)
    codigo_tombo: str | None = Field(default=None, min_length=1, max_length=50)
    estado: EstadoExemplar | None = None


class ExemplarResponse(ExemplarBase):
    id: int
    estado: EstadoExemplar

    model_config = ConfigDict(from_attributes=True)
