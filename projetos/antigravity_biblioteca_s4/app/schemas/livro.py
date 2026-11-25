from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class LivroBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=255, description="Título do livro")
    autor: str = Field(..., min_length=1, max_length=255, description="Autor do livro")
    isbn: str = Field(..., min_length=1, max_length=50, description="ISBN do livro")
    ano: int = Field(..., gt=0, lt=3000, description="Ano de publicação")
    area_conhecimento: str = Field(..., min_length=1, max_length=100, description="Área de conhecimento")


class LivroCreate(LivroBase):
    pass


class LivroUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=255)
    autor: Optional[str] = Field(None, min_length=1, max_length=255)
    isbn: Optional[str] = Field(None, min_length=1, max_length=50)
    ano: Optional[int] = Field(None, gt=0, lt=3000)
    area_conhecimento: Optional[str] = Field(None, min_length=1, max_length=100)


class LivroResponse(LivroBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
