from pydantic import BaseModel, ConfigDict, Field


class LivroBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=255, examples=["Estruturas de Dados"])
    autor: str = Field(..., min_length=1, max_length=255, examples=["Tanenbaum"])
    isbn: str = Field(..., min_length=10, max_length=20, examples=["9788577807000"])
    ano: int = Field(..., ge=1000, le=2100, examples=[2023])
    area_conhecimento: str = Field(..., min_length=2, max_length=100, examples=["Ciência da Computação"])


class LivroCreate(LivroBase):
    pass


class LivroUpdate(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=255)
    autor: str | None = Field(default=None, min_length=1, max_length=255)
    isbn: str | None = Field(default=None, min_length=10, max_length=20)
    ano: int | None = Field(default=None, ge=1000, le=2100)
    area_conhecimento: str | None = Field(default=None, min_length=2, max_length=100)


class LivroResponse(LivroBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
