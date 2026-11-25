import re
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, computed_field, field_validator

from app.enums import (
    Categoria,
    EstadoEmprestimo,
    EstadoExemplar,
    EstadoMulta,
    EstadoReserva,
    SituacaoUsuario,
)

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Titulo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Area = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Matricula = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30,
                                             pattern=r"^[A-Za-z0-9._/-]+$")]
Tombo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50,
                                         pattern=r"^[A-Za-z0-9._/-]+$")]
Id = Annotated[int, Field(gt=0)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- ISBN
def normalizar_isbn(valor: str) -> str:
    isbn = re.sub(r"[\s-]", "", valor).upper()
    if len(isbn) == 10 and re.fullmatch(r"\d{9}[\dX]", isbn):
        soma = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(isbn))
        if soma % 11 == 0:
            return isbn
    elif len(isbn) == 13 and isbn.isdigit():
        soma = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(isbn))
        if soma % 10 == 0:
            return isbn
    raise ValueError("ISBN invalido (esperado ISBN-10 ou ISBN-13 com digito verificador correto)")


def _validar_ano(ano: int | None) -> int | None:
    if ano is not None and ano > date.today().year:
        raise ValueError("ano nao pode estar no futuro")
    return ano


# ---------------------------------------------------------------- Usuario
class UsuarioCriar(Entrada):
    nome: Texto
    email: EmailStr
    matricula: Matricula
    categoria: Categoria
    situacao: SituacaoUsuario = SituacaoUsuario.ATIVO


class UsuarioAtualizar(Entrada):
    nome: Texto | None = None
    email: EmailStr | None = None
    matricula: Matricula | None = None
    categoria: Categoria | None = None
    situacao: SituacaoUsuario | None = None


class UsuarioSaida(Saida):
    id: int
    nome: str
    email: str
    matricula: str
    categoria: Categoria
    situacao: SituacaoUsuario
    suspenso_ate: date | None


# ---------------------------------------------------------------- Livro
class LivroCriar(Entrada):
    titulo: Titulo
    autor: Texto
    isbn: str
    ano: Annotated[int, Field(ge=1)]
    area: Area

    _isbn = field_validator("isbn")(normalizar_isbn)
    _ano = field_validator("ano")(_validar_ano)


class LivroAtualizar(Entrada):
    titulo: Titulo | None = None
    autor: Texto | None = None
    isbn: str | None = None
    ano: Annotated[int, Field(ge=1)] | None = None
    area: Area | None = None

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, v: str | None) -> str | None:
        return None if v is None else normalizar_isbn(v)

    _ano = field_validator("ano")(_validar_ano)


class LivroSaida(Saida):
    id: int
    titulo: str
    autor: str
    isbn: str
    ano: int
    area: str


# ---------------------------------------------------------------- Exemplar
class ExemplarCriar(Entrada):
    livro_id: Id
    tombo: Tombo
    estado: EstadoExemplar = EstadoExemplar.DISPONIVEL


class ExemplarAtualizar(Entrada):
    tombo: Tombo | None = None
    estado: EstadoExemplar | None = None


class ExemplarSaida(Saida):
    id: int
    livro_id: int
    tombo: str
    estado: EstadoExemplar


# ---------------------------------------------------------------- Emprestimo
class EmprestimoCriar(Entrada):
    usuario_id: Id
    exemplar_id: Id


class EmprestimoSaida(Saida):
    id: int
    exemplar_id: int
    usuario_id: int
    data_retirada: datetime
    data_prevista: datetime
    data_devolucao: datetime | None
    estado: EstadoEmprestimo
    renovacoes: int


# ---------------------------------------------------------------- Reserva
class ReservaCriar(Entrada):
    usuario_id: Id
    livro_id: Id


class ReservaSaida(Saida):
    id: int
    livro_id: int
    usuario_id: int
    data: datetime
    posicao: int | None
    estado: EstadoReserva
    exemplar_id: int | None
    disponivel_em: datetime | None
    expira_em: datetime | None


# ---------------------------------------------------------------- Multa
class MultaSaida(Saida):
    id: int
    emprestimo_id: int
    valor_centavos: int
    dias_atraso: int
    estado: EstadoMulta
    data_pagamento: datetime | None

    @computed_field
    @property
    def valor(self) -> str:
        """Valor em reais, formatado com duas casas decimais (ex.: "30.00")."""
        return f"{self.valor_centavos // 100}.{self.valor_centavos % 100:02d}"


# ---------------------------------------------------------------- Relatorios
class LivroMaisEmprestado(BaseModel):
    livro_id: int
    titulo: str
    autor: str
    total_emprestimos: int


class UsuarioAtrasos(BaseModel):
    usuario_id: int
    nome: str
    matricula: str
    categoria: Categoria
    emprestimos_atrasados: int
    total_dias_atraso: int


class OcupacaoArea(BaseModel):
    area: str
    total_exemplares: int
    emprestados: int
    reservados: int
    disponiveis: int
    em_reparo: int
    baixados: int
    taxa_ocupacao: float
