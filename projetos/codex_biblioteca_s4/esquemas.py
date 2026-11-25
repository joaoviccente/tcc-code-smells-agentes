from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints


Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Id = Annotated[int, Field(gt=0, strict=True)]


class Categoria(StrEnum):
    aluno = "aluno"
    professor = "professor"
    visitante = "visitante"


class Situacao(StrEnum):
    ativo = "ativo"
    suspenso = "suspenso"


class EstadoExemplar(StrEnum):
    disponivel = "disponivel"
    emprestado = "emprestado"
    reservado = "reservado"
    em_reparo = "em_reparo"
    baixado = "baixado"


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Usuario(Entrada):
    nome: Texto
    email: EmailStr
    matricula: Texto
    categoria: Categoria
    situacao: Situacao = Situacao.ativo


class Livro(Entrada):
    titulo: Texto
    autor: Texto
    isbn: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9Xx -]{10,25}$")]
    ano: Annotated[int, Field(strict=True, ge=1, le=9999)]
    area_conhecimento: Texto

    def model_post_init(self, context):
        isbn = self.isbn.replace("-", "").replace(" ", "").upper()
        if not ((len(isbn) == 13 and isbn.isascii() and isbn.isdigit()) or
                (len(isbn) == 10 and isbn[:9].isdigit() and
                 (isbn[-1].isdigit() or isbn[-1] == "X"))):
            raise ValueError("Informe um ISBN de 10 ou 13 caracteres.")
        self.isbn = isbn


class Exemplar(Entrada):
    livro_id: Id
    codigo_tombo: Texto
    estado: EstadoExemplar = EstadoExemplar.disponivel


class NovoEmprestimo(Entrada):
    usuario_id: Id
    exemplar_id: Id


class NovaReserva(Entrada):
    usuario_id: Id
    livro_id: Id


class Periodo(Entrada):
    inicio: date
    fim: date

    def model_post_init(self, context):
        if self.fim < self.inicio:
            raise ValueError("A data final deve ser igual ou posterior à inicial.")
