from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class LivroBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=255, description="Título da obra")
    autor: str = Field(..., min_length=1, max_length=255, description="Autor da obra")
    isbn: str = Field(..., min_length=1, max_length=50, description="Código ISBN")
    ano: int = Field(..., gt=0, le=2100, description="Ano de publicação")
    area: str = Field(..., min_length=1, max_length=100, description="Área de conhecimento")


class LivroCreate(LivroBase):
    pass


class LivroUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=255)
    autor: Optional[str] = Field(None, min_length=1, max_length=255)
    isbn: Optional[str] = Field(None, min_length=1, max_length=50)
    ano: Optional[int] = Field(None, gt=0, le=2100)
    area: Optional[str] = Field(None, min_length=1, max_length=100)


class LivroResponse(LivroBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
