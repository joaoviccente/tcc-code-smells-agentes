import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, StringConstraints,
    field_validator,
)

Categoria = Literal["aluno", "professor", "visitante"]
Situacao = Literal["ativo", "suspenso"]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Dinheiro = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float)]


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------- Usuario
class UsuarioCriar(_Entrada):
    nome: Annotated[Texto, StringConstraints(max_length=200)]
    email: EmailStr
    matricula: Annotated[Texto, StringConstraints(max_length=50, pattern=r"^[A-Za-z0-9.\-/]+$")]
    categoria: Categoria
    situacao: Situacao = "ativo"


class UsuarioAtualizar(_Entrada):
    nome: Annotated[Texto, StringConstraints(max_length=200)] | None = None
    email: EmailStr | None = None
    matricula: Annotated[Texto, StringConstraints(max_length=50, pattern=r"^[A-Za-z0-9.\-/]+$")] | None = None
    categoria: Categoria | None = None
    situacao: Situacao | None = None


class UsuarioSaida(_Saida):
    id: int
    nome: str
    email: str
    matricula: str
    categoria: str
    situacao: str
    suspenso_ate: datetime | None
    motivo_suspensao: str | None


# ------------------------------------------------------------------- Livro
def normalizar_isbn(valor: str) -> str:
    isbn = re.sub(r"[\s\-]", "", valor).upper()
    if len(isbn) == 10 and re.fullmatch(r"\d{9}[\dX]", isbn):
        soma = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(isbn))
        if soma % 11 == 0:
            return isbn
    elif len(isbn) == 13 and isbn.isdigit():
        soma = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(isbn))
        if soma % 10 == 0:
            return isbn
    raise ValueError("ISBN invalido (esperado ISBN-10 ou ISBN-13 com digito verificador correto)")


def _validar_ano(ano: int) -> int:
    if ano > datetime.now().year + 1:
        raise ValueError("ano nao pode estar no futuro")
    return ano


class LivroCriar(_Entrada):
    titulo: Annotated[Texto, StringConstraints(max_length=300)]
    autor: Annotated[Texto, StringConstraints(max_length=200)]
    isbn: str
    ano: int = Field(ge=1450)
    area_conhecimento: Annotated[Texto, StringConstraints(max_length=100)]

    _isbn = field_validator("isbn")(normalizar_isbn)
    _ano = field_validator("ano")(_validar_ano)


class LivroAtualizar(_Entrada):
    titulo: Annotated[Texto, StringConstraints(max_length=300)] | None = None
    autor: Annotated[Texto, StringConstraints(max_length=200)] | None = None
    isbn: str | None = None
    ano: int | None = Field(default=None, ge=1450)
    area_conhecimento: Annotated[Texto, StringConstraints(max_length=100)] | None = None

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, v):
        return None if v is None else normalizar_isbn(v)

    @field_validator("ano")
    @classmethod
    def _ano(cls, v):
        return None if v is None else _validar_ano(v)


class LivroSaida(_Saida):
    id: int
    titulo: str
    autor: str
    isbn: str
    ano: int
    area_conhecimento: str


# ---------------------------------------------------------------- Exemplar
class ExemplarCriar(_Entrada):
    livro_id: int = Field(gt=0)
    codigo_tombo: Annotated[Texto, StringConstraints(max_length=50)]
    # Estados "emprestado" e "reservado" so sao atingidos pelas operacoes de negocio.
    estado: Literal["disponivel", "em_reparo"] = "disponivel"


class ExemplarAtualizar(_Entrada):
    codigo_tombo: Annotated[Texto, StringConstraints(max_length=50)] | None = None
    estado: Literal["disponivel", "em_reparo", "baixado"] | None = None


class ExemplarSaida(_Saida):
    id: int
    livro_id: int
    codigo_tombo: str
    estado: str


# -------------------------------------------------------------- Emprestimo
class EmprestimoCriar(_Entrada):
    usuario_id: int = Field(gt=0)
    exemplar_id: int = Field(gt=0)


class MultaSaida(_Saida):
    id: int
    emprestimo_id: int
    valor: Dinheiro
    estado: str
    dias_atraso: int
    data_geracao: datetime
    data_pagamento: datetime | None


class EmprestimoSaida(_Saida):
    id: int
    exemplar_id: int
    usuario_id: int
    data_retirada: datetime
    data_prevista: date
    data_devolucao: datetime | None
    estado: str
    numero_renovacoes: int
    dias_atraso: int
    multa: MultaSaida | None = None


# ----------------------------------------------------------------- Reserva
class ReservaCriar(_Entrada):
    usuario_id: int = Field(gt=0)
    livro_id: int = Field(gt=0)


class ReservaSaida(_Saida):
    id: int
    livro_id: int
    usuario_id: int
    data_reserva: datetime
    posicao_fila: int | None
    estado: str
    exemplar_id: int | None
    data_disponibilizacao: datetime | None
    expira_em: datetime | None


# -------------------------------------------------------------- Relatorios
class LivroMaisEmprestado(BaseModel):
    livro_id: int
    titulo: str
    autor: str
    total_emprestimos: int


class UsuarioAtrasos(BaseModel):
    usuario_id: int
    nome: str
    matricula: str
    categoria: str
    quantidade_atrasos: int
    total_dias_atraso: int


class OcupacaoArea(BaseModel):
    area_conhecimento: str
    total_exemplares: int
    emprestados: int
    reservados: int
    disponiveis: int
    em_reparo: int
    taxa_ocupacao: float = Field(description="Percentual de exemplares emprestados sobre o acervo ativo (exclui baixados)")
