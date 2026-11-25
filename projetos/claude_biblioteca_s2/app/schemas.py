import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    StringConstraints,
    field_validator,
)

from . import relogio
from .enums import (
    Categoria,
    EstadoEmprestimo,
    EstadoExemplar,
    EstadoMulta,
    EstadoReserva,
    SituacaoUsuario,
)

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Dinheiro = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]
IdPositivo = Annotated[int, Field(gt=0)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- usuarios
Matricula = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30,
                                             pattern=r"^[A-Za-z0-9.\-/]+$")]
Nome = Annotated[Texto, StringConstraints(max_length=120)]


class UsuarioCriar(Entrada):
    nome: Nome
    email: EmailStr
    matricula: Matricula
    categoria: Categoria
    situacao: SituacaoUsuario = SituacaoUsuario.ativo


class UsuarioAtualizar(Entrada):
    nome: Nome | None = None
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
    suspensao_ate: date | None


# --------------------------------------------------------------------------- livros
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
    if ano is not None and ano > relogio.agora().year:
        raise ValueError("ano nao pode ser posterior ao ano corrente")
    return ano


class LivroCriar(Entrada):
    titulo: Annotated[Texto, StringConstraints(max_length=300)]
    autor: Annotated[Texto, StringConstraints(max_length=200)]
    isbn: str
    ano: Annotated[int, Field(ge=1450)]
    area_conhecimento: Annotated[Texto, StringConstraints(max_length=100)]

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, v):
        return v if v is None else normalizar_isbn(v)

    @field_validator("ano")
    @classmethod
    def _ano(cls, v):
        return _validar_ano(v)


class LivroAtualizar(Entrada):
    titulo: Annotated[Texto, StringConstraints(max_length=300)] | None = None
    autor: Annotated[Texto, StringConstraints(max_length=200)] | None = None
    isbn: str | None = None
    ano: Annotated[int, Field(ge=1450)] | None = None
    area_conhecimento: Annotated[Texto, StringConstraints(max_length=100)] | None = None

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, v):
        return v if v is None else normalizar_isbn(v)

    @field_validator("ano")
    @classmethod
    def _ano(cls, v):
        return _validar_ano(v)


class LivroSaida(Saida):
    id: int
    titulo: str
    autor: str
    isbn: str
    ano: int
    area_conhecimento: str


# --------------------------------------------------------------------------- exemplares
CodigoTombo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class ExemplarCriar(Entrada):
    livro_id: IdPositivo
    codigo_tombo: CodigoTombo
    estado: EstadoExemplar = Field(
        EstadoExemplar.disponivel,
        description="Estado inicial: apenas 'disponivel' ou 'em_reparo'.",
    )

    @field_validator("estado")
    @classmethod
    def _estado_inicial(cls, v):
        if v not in (EstadoExemplar.disponivel, EstadoExemplar.em_reparo):
            raise ValueError("estado inicial deve ser 'disponivel' ou 'em_reparo'")
        return v


class ExemplarAtualizar(Entrada):
    codigo_tombo: CodigoTombo | None = None
    estado: EstadoExemplar | None = Field(
        None,
        description="Transicoes manuais permitidas: 'disponivel', 'em_reparo' e 'baixado'. "
                    "'emprestado' e 'reservado' sao controlados pelo sistema.",
    )

    @field_validator("estado")
    @classmethod
    def _estado_manual(cls, v):
        if v in (EstadoExemplar.emprestado, EstadoExemplar.reservado):
            raise ValueError("os estados 'emprestado' e 'reservado' sao definidos apenas pelo sistema")
        return v


class ExemplarSaida(Saida):
    id: int
    livro_id: int
    codigo_tombo: str
    estado: EstadoExemplar


# --------------------------------------------------------------------------- multas
class MultaSaida(Saida):
    id: int
    emprestimo_id: int
    usuario_id: int
    valor: Dinheiro
    dias_atraso: int
    estado: EstadoMulta
    valor_definitivo: bool
    data_geracao: datetime
    data_pagamento: datetime | None


class PagamentoMulta(Entrada):
    valor: Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)] | None = Field(
        None, description="Opcional. Se informado, deve ser igual ao valor da multa."
    )


# --------------------------------------------------------------------------- emprestimos
class EmprestimoCriar(Entrada):
    usuario_id: IdPositivo
    exemplar_id: IdPositivo


class EmprestimoSaida(Saida):
    id: int
    exemplar_id: int
    livro_id: int
    usuario_id: int
    categoria_usuario: Categoria
    data_retirada: datetime
    data_prevista: date
    data_devolucao: datetime | None
    estado: EstadoEmprestimo
    renovacoes: int
    dias_atraso: int
    multa: MultaSaida | None


# --------------------------------------------------------------------------- reservas
class ReservaCriar(Entrada):
    usuario_id: IdPositivo
    livro_id: IdPositivo


class ReservaSaida(Saida):
    id: int
    livro_id: int
    usuario_id: int
    data_reserva: datetime
    posicao: int | None
    estado: EstadoReserva
    exemplar_id: int | None
    disponivel_em: datetime | None
    expira_em: datetime | None
    encerrada_em: datetime | None


# --------------------------------------------------------------------------- relatorios
class LivroMaisEmprestado(BaseModel):
    livro_id: int
    titulo: str
    autor: str
    isbn: str
    total_emprestimos: int


class UsuarioComAtrasos(BaseModel):
    usuario_id: int
    nome: str
    matricula: str
    categoria: Categoria
    quantidade_atrasos: int
    total_dias_atraso: int


class OcupacaoArea(BaseModel):
    area_conhecimento: str
    total_exemplares: int = Field(description="Exemplares no acervo (exclui baixados)")
    emprestados: int
    reservados: int
    disponiveis: int
    em_reparo: int
    baixados: int
    taxa_ocupacao: float = Field(description="Percentual: emprestados / total_exemplares * 100")


class Erro(BaseModel):
    detail: str
