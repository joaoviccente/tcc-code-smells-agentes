from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class LivroBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=255)
    autor: str = Field(..., min_length=1, max_length=255)
    isbn: str = Field(..., min_length=5, max_length=30)
    ano: int = Field(..., ge=1000, le=2100)
    area_conhecimento: str = Field(..., min_length=1, max_length=100)


class LivroCreate(LivroBase):
    pass


class LivroUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=255)
    autor: Optional[str] = Field(None, min_length=1, max_length=255)
    isbn: Optional[str] = Field(None, min_length=5, max_length=30)
    ano: Optional[int] = Field(None, ge=1000, le=2100)
    area_conhecimento: Optional[str] = Field(None, min_length=1, max_length=100)


class LivroResponse(LivroBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
