import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Categoria = Literal["aluno", "professor", "visitante"]
SituacaoUsuario = Literal["ativo", "suspenso"]
EstadoExemplarManual = Literal["disponivel", "em_reparo", "baixado"]

Texto = lambda n: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=n)]  # noqa: E731
Matricula = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9.\-/]{3,30}$")]
CodigoTombo = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9.\-/]{1,50}$")]

ANO_MINIMO = 1450  # prensa de Gutenberg


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


def normalizar_isbn(valor: str) -> str:
    isbn = re.sub(r"[\s-]", "", valor).upper()
    if re.fullmatch(r"\d{9}[\dX]", isbn):
        soma = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(isbn))
        if soma % 11 == 0:
            return isbn
    elif re.fullmatch(r"\d{13}", isbn):
        soma = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(isbn))
        if soma % 10 == 0:
            return isbn
    raise ValueError("ISBN invalido: informe um ISBN-10 ou ISBN-13 com digito verificador correto")


def validar_ano(ano: int) -> int:
    if not (ANO_MINIMO <= ano <= date.today().year + 1):
        raise ValueError(f"ano deve estar entre {ANO_MINIMO} e {date.today().year + 1}")
    return ano


# ---------------------------------------------------------------- Usuario
class UsuarioCriar(Entrada):
    nome: Texto(150)
    email: EmailStr
    matricula: Matricula
    categoria: Categoria
    situacao: SituacaoUsuario = "ativo"


class UsuarioAtualizar(Entrada):
    nome: Texto(150) | None = None
    email: EmailStr | None = None
    matricula: Matricula | None = None
    categoria: Categoria | None = None
    situacao: SituacaoUsuario | None = None


class UsuarioSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    email: str
    matricula: str
    categoria: Categoria
    situacao: SituacaoUsuario
    suspensao_automatica: bool
    suspenso_ate: date | None


# ---------------------------------------------------------------- Livro
class LivroCriar(Entrada):
    titulo: Texto(300)
    autor: Texto(200)
    isbn: str
    ano: int
    area_conhecimento: Texto(100)

    _isbn = field_validator("isbn")(normalizar_isbn)
    _ano = field_validator("ano")(validar_ano)


class LivroAtualizar(Entrada):
    titulo: Texto(300) | None = None
    autor: Texto(200) | None = None
    isbn: str | None = None
    ano: int | None = None
    area_conhecimento: Texto(100) | None = None

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, v):
        return None if v is None else normalizar_isbn(v)

    @field_validator("ano")
    @classmethod
    def _ano(cls, v):
        return None if v is None else validar_ano(v)


class LivroSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    titulo: str
    autor: str
    isbn: str
    ano: int
    area_conhecimento: str


# ---------------------------------------------------------------- Exemplar
class ExemplarCriar(Entrada):
    livro_id: int = Field(gt=0)
    codigo_tombo: CodigoTombo
    estado: Literal["disponivel", "em_reparo"] = "disponivel"


class ExemplarAtualizar(Entrada):
    codigo_tombo: CodigoTombo | None = None
    # "emprestado" e "reservado" sao controlados exclusivamente pelo sistema.
    estado: EstadoExemplarManual | None = None


class ExemplarSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    livro_id: int
    codigo_tombo: str
    estado: str


# ---------------------------------------------------------------- Emprestimo
class EmprestimoCriar(Entrada):
    usuario_id: int = Field(gt=0)
    exemplar_id: int = Field(gt=0)


class MultaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    emprestimo_id: int
    valor: Decimal
    estado: str
    data_pagamento: datetime | None


class EmprestimoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    exemplar_id: int
    usuario_id: int
    data_retirada: datetime
    data_prevista: date
    data_devolucao: datetime | None
    estado: str
    numero_renovacoes: int
    dias_atraso: int
    multa: MultaSaida | None


# ---------------------------------------------------------------- Reserva
class ReservaCriar(Entrada):
    usuario_id: int = Field(gt=0)
    livro_id: int = Field(gt=0)


class ReservaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    livro_id: int
    usuario_id: int
    data: datetime
    estado: str
    posicao_fila: int | None
    exemplar_id: int | None
    expira_em: datetime | None


# ---------------------------------------------------------------- Multa
class PagamentoEntrada(Entrada):
    # Opcional; se informado, deve coincidir com o valor da multa (sem pagamento parcial).
    valor: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)


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
    categoria: str
    total_atrasos: int
    total_dias_atraso: int


class OcupacaoArea(BaseModel):
    area_conhecimento: str
    total_exemplares: int
    emprestados: int
    reservados: int
    disponiveis: int
    em_reparo: int
    baixados: int
    taxa_ocupacao: float
