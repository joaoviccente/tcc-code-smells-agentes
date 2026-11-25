import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_validator

# Valores monetarios: Decimal com no maximo 2 casas na entrada; numero JSON na saida.
Valor = Annotated[
    Decimal,
    Field(max_digits=15, decimal_places=2),
    PlainSerializer(lambda v: float(v), return_type=float, when_used="json"),
]
ValorPositivo = Annotated[Valor, Field(gt=0)]
ValorNaoNegativo = Annotated[Valor, Field(ge=0)]

Categoria = Literal["comum", "premium", "empresarial"]
SituacaoCliente = Literal["ativo", "bloqueado"]
TipoConta = Literal["corrente", "poupanca"]
MesReferencia = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-11"])]


def validar_cpf(cpf: str) -> str:
    digitos = re.sub(r"\D", "", cpf)
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        raise ValueError("CPF invalido")
    for n in (9, 10):
        soma = sum(int(digitos[i]) * (n + 1 - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(digitos[n]):
            raise ValueError("CPF invalido")
    return digitos


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Clientes ----------
class ClienteCriar(Entrada):
    nome: str = Field(min_length=2, max_length=120)
    cpf: str
    email: EmailStr
    categoria: Categoria

    _cpf = field_validator("cpf")(validar_cpf)


class ClienteAtualizar(Entrada):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    categoria: Categoria | None = None
    situacao: SituacaoCliente | None = None


class ClienteSaida(Saida):
    id: int
    nome: str
    cpf: str
    email: str
    categoria: str
    situacao: str
    criado_em: datetime


# ---------- Contas ----------
class ContaCriar(Entrada):
    cliente_id: int = Field(gt=0)
    tipo: TipoConta
    limite_credito: ValorNaoNegativo = Decimal("0.00")


class ContaAtualizar(Entrada):
    limite_credito: ValorNaoNegativo | None = None
    estado: Literal["ativa", "bloqueada"] | None = None


class ContaSaida(Saida):
    id: int
    numero: str
    cliente_id: int
    tipo: str
    saldo: Valor
    limite_credito: Valor
    estado: str
    negativo_desde: datetime | None
    criada_em: datetime
    encerrada_em: datetime | None


# ---------- Cartoes ----------
class CartaoCriar(Entrada):
    conta_id: int = Field(gt=0)
    limite: ValorNaoNegativo


class CartaoAtualizar(Entrada):
    limite: ValorNaoNegativo | None = None
    estado: Literal["ativo", "bloqueado"] | None = None


class CartaoSaida(Saida):
    id: int
    numero: str
    conta_id: int
    limite: Valor
    estado: str
    criado_em: datetime


# ---------- Transacoes ----------
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
    conta_id: int
    conta_destino_id: int | None
    tipo: str
    valor: Valor
    data: datetime
    estado: str
    transacao_original_id: int | None
    descricao: str | None


class TarifaSaida(Saida):
    id: int
    conta_id: int
    tipo: str
    valor: Valor
    estado: str
    mes_referencia: str
    transacao_id: int | None
    criada_em: datetime
    cobrada_em: datetime | None


class OperacaoSaida(BaseModel):
    transacao: TransacaoSaida
    tarifa: TarifaSaida | None = None
    saldo_conta: Valor


class LancamentoExtrato(BaseModel):
    transacao: TransacaoSaida
    natureza: Literal["credito", "debito"]
    efeito: Valor


class ExtratoSaida(BaseModel):
    conta_id: int
    numero: str
    saldo_atual: Valor
    limite_credito: Valor
    inicio: datetime | None
    fim: datetime | None
    lancamentos: list[LancamentoExtrato]


# ---------- Faturas ----------
class FaturaCriar(Entrada):
    mes_referencia: MesReferencia
    valor: ValorNaoNegativo
    vencimento: date | None = None


class FaturaSaida(Saida):
    id: int
    cartao_id: int
    mes_referencia: str
    valor: Valor
    juros: Valor
    vencimento: date
    estado: str
    pago_em: datetime | None
    valor_pago: Valor | None
    total_devido: Valor


# ---------- Rotinas ----------
class RotinaSaida(BaseModel):
    data_referencia: datetime
    faturas_atrasadas: int
    cartoes_bloqueados: int
    clientes_bloqueados: int
    tarifas_mensais_geradas: int
    tarifas_pendentes_cobradas: int


# ---------- Relatorios ----------
class ClienteMovimentacao(BaseModel):
    cliente_id: int
    nome: str
    categoria: str
    quantidade_transacoes: int
    total_movimentado: Valor


class ContaNegativa(BaseModel):
    conta_id: int
    numero: str
    cliente_id: int
    cliente_nome: str
    saldo: Valor
    limite_credito: Valor
    negativo_desde: datetime | None
    dias_negativo: int


class ReceitaCategoria(BaseModel):
    categoria: str
    quantidade_tarifas: int
    receita: Valor
