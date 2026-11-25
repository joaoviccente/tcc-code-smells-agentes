import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (BaseModel, ConfigDict, EmailStr, Field, StringConstraints, computed_field,
                      field_validator)

from app import relogio
from app.models import (Categoria, EstadoEmprestimo, EstadoExemplar, EstadoMulta, EstadoReserva,
                        SituacaoUsuario)



def Texto(maximo: int, minimo: int = 1):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=minimo, max_length=maximo)]


Matricula = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9.\-/]{3,30}$")]
CodigoTombo = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9.\-/]{1,50}$")]

# Estados que podem ser atribuidos manualmente a um exemplar (emprestado/reservado sao controlados pelo sistema)
EstadoExemplarManual = Literal["disponivel", "em_reparo", "baixado"]
EstadoExemplarInicial = Literal["disponivel", "em_reparo"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def normalizar_isbn(valor: str) -> str:
    s = re.sub(r"[\s\-]", "", valor).upper()
    if re.fullmatch(r"[0-9]{9}[0-9X]", s):
        total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(s))
        if total % 11 == 0:
            return s
    elif re.fullmatch(r"[0-9]{13}", s):
        total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s))
        if total % 10 == 0:
            return s
    raise ValueError("ISBN invalido (esperado ISBN-10 ou ISBN-13 com digito verificador correto)")


def _validar_ano(ano: int | None) -> int | None:
    if ano is not None and not (1450 <= ano <= relogio.agora().year):
        raise ValueError(f"ano deve estar entre 1450 e {relogio.agora().year}")
    return ano


# ---------------- Usuario ----------------
class UsuarioCriar(Entrada):
    nome: Texto(150, 2)
    email: EmailStr
    matricula: Matricula
    categoria: Categoria
    situacao: SituacaoUsuario = SituacaoUsuario.ATIVO


class UsuarioAtualizar(Entrada):
    nome: Texto(150, 2) | None = None
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


# ---------------- Livro ----------------
class LivroCriar(Entrada):
    titulo: Texto(255)
    autor: Texto(255)
    isbn: str
    ano: int
    area: Texto(100, 2)

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, v: str) -> str:
        return normalizar_isbn(v)

    @field_validator("ano")
    @classmethod
    def _ano(cls, v: int) -> int:
        return _validar_ano(v)


class LivroAtualizar(Entrada):
    titulo: Texto(255) | None = None
    autor: Texto(255) | None = None
    isbn: str | None = None
    ano: int | None = None
    area: Texto(100, 2) | None = None

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, v: str | None) -> str | None:
        return None if v is None else normalizar_isbn(v)

    @field_validator("ano")
    @classmethod
    def _ano(cls, v: int | None) -> int | None:
        return _validar_ano(v)


class LivroSaida(Saida):
    id: int
    titulo: str
    autor: str
    isbn: str
    ano: int
    area: str


# ---------------- Exemplar ----------------
class ExemplarCriar(Entrada):
    livro_id: int = Field(gt=0)
    codigo_tombo: CodigoTombo
    estado: EstadoExemplarInicial = "disponivel"


class ExemplarSubstituir(Entrada):
    codigo_tombo: CodigoTombo
    estado: EstadoExemplarManual


class ExemplarAtualizar(Entrada):
    codigo_tombo: CodigoTombo | None = None
    estado: EstadoExemplarManual | None = None


class ExemplarSaida(Saida):
    id: int
    livro_id: int
    codigo_tombo: str
    estado: EstadoExemplar


# ---------------- Emprestimo ----------------
class EmprestimoCriar(Entrada):
    usuario_id: int = Field(gt=0)
    exemplar_id: int = Field(gt=0)


class EmprestimoSaida(Saida):
    id: int
    exemplar_id: int
    livro_id: int
    usuario_id: int
    data_retirada: date
    data_prevista: date
    data_devolucao: date | None
    estado: EstadoEmprestimo
    renovacoes: int


# ---------------- Reserva ----------------
class ReservaCriar(Entrada):
    usuario_id: int = Field(gt=0)
    livro_id: int = Field(gt=0)


class ReservaSaida(Saida):
    id: int
    livro_id: int
    usuario_id: int
    data: datetime
    posicao: int | None
    estado: EstadoReserva
    exemplar_id: int | None
    expira_em: datetime | None


# ---------------- Multa ----------------
class MultaSaida(Saida):
    id: int
    emprestimo_id: int
    usuario_id: int
    dias_atraso: int
    estado: EstadoMulta
    data_pagamento: datetime | None
    valor_centavos: int = Field(exclude=True)

    @computed_field
    @property
    def valor(self) -> Decimal:
        return (Decimal(self.valor_centavos) / 100).quantize(Decimal("0.01"))


# ---------------- Relatorios ----------------
class LivroMaisEmprestado(BaseModel):
    livro_id: int
    titulo: str
    autor: str
    total_emprestimos: int


class UsuarioAtrasos(BaseModel):
    usuario_id: int
    nome: str
    categoria: Categoria
    emprestimos_atrasados: int
    total_dias_atraso: int


class OcupacaoArea(BaseModel):
    area: str
    total_exemplares: int
    disponiveis: int
    emprestados: int
    reservados: int
    em_reparo: int
    taxa_ocupacao: float = Field(description="Percentual de exemplares emprestados sobre o acervo nao baixado")
