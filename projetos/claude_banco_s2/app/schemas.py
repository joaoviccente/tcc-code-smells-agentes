import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import (
    CategoriaCliente, EstadoCartao, EstadoConta, EstadoFatura, EstadoTarifa,
    EstadoTransacao, MotivoBloqueioCartao, SituacaoCliente, TipoConta, TipoTarifa,
    TipoTransacao,
)

ValorPositivo = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=2)]
ValorNaoNegativo = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=2)]
Nome = Annotated[str, Field(min_length=3, max_length=120)]
PADRAO_MES = r"^\d{4}-(0[1-9]|1[0-2])$"
MesReferencia = Annotated[str, Field(pattern=PADRAO_MES, examples=["2026-11"])]

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def cpf_valido(cpf: str) -> bool:
    if len(cpf) != 11 or not cpf.isdigit() or cpf == cpf[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(cpf[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(cpf[n]):
            return False
    return True


def _validar_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not _EMAIL_RE.match(v):
        raise ValueError("e-mail invalido")
    return v


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- clientes
class ClienteCriar(Entrada):
    nome: Nome
    cpf: str = Field(examples=["529.982.247-25"])
    email: str = Field(examples=["fulano@exemplo.com"])
    categoria: CategoriaCliente

    @field_validator("cpf")
    @classmethod
    def _cpf(cls, v: str) -> str:
        digitos = re.sub(r"[.\-\s]", "", v)
        if not cpf_valido(digitos):
            raise ValueError("CPF invalido")
        return digitos

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _validar_email(v)


class ClienteAtualizar(Entrada):
    nome: Nome | None = None
    email: str | None = None
    categoria: CategoriaCliente | None = None
    situacao: SituacaoCliente | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return None if v is None else _validar_email(v)


class ClienteSaida(Saida):
    id: int
    nome: str
    cpf: str
    email: str
    categoria: CategoriaCliente
    situacao: SituacaoCliente
    criado_em: datetime


# ------------------------------------------------------------------ contas
class ContaCriar(Entrada):
    cliente_id: int = Field(gt=0)
    tipo: TipoConta
    limite_credito: ValorNaoNegativo = Decimal("0.00")


class ContaAtualizar(Entrada):
    limite_credito: ValorNaoNegativo | None = None
    estado: EstadoConta | None = Field(
        default=None, description="ativa ou bloqueada (encerramento via DELETE)"
    )


class ContaSaida(Saida):
    id: int
    numero: str
    cliente_id: int
    tipo: TipoConta
    saldo: Decimal
    limite_credito: Decimal
    estado: EstadoConta
    negativo_desde: datetime | None
    criada_em: datetime
    encerrada_em: datetime | None


# ----------------------------------------------------------------- tarifas
class TarifaSaida(Saida):
    id: int
    conta_id: int
    tipo: TipoTarifa
    valor: Decimal
    estado: EstadoTarifa
    categoria: CategoriaCliente
    competencia: str
    transacao_id: int | None
    criada_em: datetime
    cobrada_em: datetime | None


# -------------------------------------------------------------- transacoes
class DepositoEntrada(Entrada):
    conta_id: int = Field(gt=0)
    valor: ValorPositivo
    descricao: str | None = Field(default=None, max_length=200)


class SaqueEntrada(DepositoEntrada):
    pass


class TransferenciaEntrada(Entrada):
    conta_origem_id: int = Field(gt=0)
    conta_destino_id: int = Field(gt=0)
    valor: ValorPositivo
    descricao: str | None = Field(default=None, max_length=200)


class TransacaoSaida(Saida):
    id: int
    tipo: TipoTransacao
    conta_id: int
    conta_destino_id: int | None
    valor: Decimal
    data: datetime
    estado: EstadoTransacao
    transacao_original_id: int | None
    descricao: str | None
    tarifa: TarifaSaida | None = None


class LancamentoExtrato(TransacaoSaida):
    efeito: Decimal = Field(description="Impacto no saldo da conta (+ credito, - debito)")


class Extrato(BaseModel):
    conta_id: int
    numero: str
    saldo_atual: Decimal
    inicio: date | None
    fim: date | None
    lancamentos: list[LancamentoExtrato]


# ----------------------------------------------------------------- cartoes
class CartaoCriar(Entrada):
    conta_id: int = Field(gt=0)
    limite: ValorNaoNegativo


class CartaoAtualizar(Entrada):
    limite: ValorNaoNegativo | None = None
    estado: EstadoCartao | None = Field(
        default=None, description="ativo ou bloqueado (cancelamento via DELETE)"
    )


class CartaoSaida(Saida):
    id: int
    conta_id: int
    numero: str
    limite: Decimal
    estado: EstadoCartao
    motivo_bloqueio: MotivoBloqueioCartao | None
    criado_em: datetime


# ----------------------------------------------------------------- faturas
class FaturaCriar(Entrada):
    mes_referencia: MesReferencia
    valor: ValorPositivo
    data_vencimento: date | None = Field(
        default=None, description="Padrao: dia 10 do mes seguinte ao de referencia"
    )


class PagamentoFatura(Entrada):
    valor: ValorPositivo


class FaturaSaida(Saida):
    id: int
    cartao_id: int
    mes_referencia: str
    valor: Decimal
    juros: Decimal
    valor_total: Decimal
    data_vencimento: date
    estado: EstadoFatura
    dias_atraso: int
    data_pagamento: datetime | None
    valor_pago: Decimal | None


# -------------------------------------------------------------- relatorios
class MovimentacaoCliente(BaseModel):
    cliente_id: int
    nome: str
    categoria: CategoriaCliente
    quantidade_transacoes: int
    valor_movimentado: Decimal


class ContaNegativa(BaseModel):
    conta_id: int
    numero: str
    cliente_id: int
    cliente_nome: str
    categoria: CategoriaCliente
    saldo: Decimal
    limite_credito: Decimal
    negativo_desde: datetime | None
    dias_negativo: int


class ReceitaCategoria(BaseModel):
    categoria: CategoriaCliente
    quantidade: int
    total: Decimal


class ReceitaTarifas(BaseModel):
    inicio: date | None
    fim: date | None
    por_categoria: list[ReceitaCategoria]
    total_geral: Decimal


class ResultadoRotina(BaseModel):
    data_referencia: datetime
    detalhes: dict[str, int]
