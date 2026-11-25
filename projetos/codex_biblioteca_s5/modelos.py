from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PositiveInt, StringConstraints, field_validator

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Categoria = Literal["aluno", "professor", "visitante"]
EstadoExemplar = Literal["disponivel", "emprestado", "reservado", "em_reparo", "baixado"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Usuario(Entrada):
    nome: Texto
    email: EmailStr
    matricula: Texto
    categoria: Categoria
    situacao: Literal["ativo", "suspenso"] = "ativo"


class Livro(Entrada):
    titulo: Texto
    autor: Texto
    isbn: Texto
    ano: Annotated[int, Field(ge=1, le=9999)]
    area_conhecimento: Texto

    @field_validator("isbn")
    @classmethod
    def validar_isbn(cls, valor: str) -> str:
        isbn = valor.replace("-", "").replace(" ", "").upper()
        if len(isbn) == 10 and isbn[:9].isascii() and isbn[:9].isdigit():
            if isbn[-1] in "0123456789X":
                digitos = [int(d) if d != "X" else 10 for d in isbn]
                if sum((10 - i) * d for i, d in enumerate(digitos)) % 11 == 0:
                    return isbn
        if len(isbn) == 13 and isbn.isascii() and isbn.isdigit() and isbn.startswith(("978", "979")):
            if sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(isbn)) % 10 == 0:
                return isbn
        raise ValueError("Informe um ISBN-10 ou ISBN-13 valido")


class Exemplar(Entrada):
    livro_id: PositiveInt
    codigo_tombo: Texto
    estado: EstadoExemplar = "disponivel"


class NovoEmprestimo(Entrada):
    exemplar_id: PositiveInt
    usuario_id: PositiveInt


class NovaReserva(Entrada):
    livro_id: PositiveInt
    usuario_id: PositiveInt
