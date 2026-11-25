from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_validator

from app.models import (
    CategoriaCliente, EstadoCartao, EstadoConta, EstadoFatura, EstadoTarifa, EstadoTransacao,
    SituacaoCliente, TipoConta, TipoTarifa, TipoTransacao,
)

# ---------- tipos auxiliares ----------
Dinheiro = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]
ValorPositivo = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=2)]
ValorNaoNegativo = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=2)]
MesReferencia = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-11"])]
Nome = Annotated[str, Field(min_length=3, max_length=120)]
Descricao = Annotated[str | None, Field(default=None, max_length=200)]


def validar_cpf(valor: str) -> str:
    cpf = "".join(c for c in valor if c.isdigit())
    if len(cpf) != 11 or len(set(cpf)) == 1 or any(c not in "0123456789.- " for c in valor):
        raise ValueError("CPF invalido")
    for n in (9, 10):
        soma = sum(int(cpf[i]) * (n + 1 - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(cpf[n]):
            raise ValueError("CPF invalido")
    return cpf


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- clientes ----------
class ClienteCreate(Entrada):
    nome: Nome
    cpf: str
    email: EmailStr
    categoria: CategoriaCliente = CategoriaCliente.COMUM

    _cpf = field_validator("cpf")(validar_cpf)


class ClienteUpdate(Entrada):
    nome: Nome | None = None
    email: EmailStr | None = None
    categoria: CategoriaCliente | None = None
    situacao: SituacaoCliente | None = None


class ClienteOut(Saida):
    id: int
    nome: str
    cpf: str
    email: str
    categoria: CategoriaCliente
    situacao: SituacaoCliente
    criado_em: datetime


# ---------- contas ----------
class ContaCreate(Entrada):
    cliente_id: int = Field(gt=0)
    tipo: TipoConta = TipoConta.CORRENTE
    limite_credito: ValorNaoNegativo = Decimal("0.00")


class ContaUpdate(Entrada):
    limite_credito: ValorNaoNegativo | None = None
    estado: Literal["ativa", "bloqueada"] | None = None


class ContaOut(Saida):
    id: int
    numero: str
    cliente_id: int
    tipo: TipoConta
    saldo: Dinheiro
    limite_credito: Dinheiro
    saldo_disponivel: Dinheiro
    estado: EstadoConta
    negativo_desde: datetime | None
    criado_em: datetime
    encerrado_em: datetime | None


# ---------- cartoes ----------
class CartaoCreate(Entrada):
    conta_id: int = Field(gt=0)
    limite: ValorNaoNegativo


class CartaoUpdate(Entrada):
    limite: ValorNaoNegativo | None = None
    estado: Literal["ativo", "bloqueado"] | None = None


class CartaoOut(Saida):
    id: int
    conta_id: int
    numero: str
    limite: Dinheiro
    estado: EstadoCartao
    motivo_bloqueio: str | None
    criado_em: datetime


# ---------- transacoes ----------
class DepositoIn(Entrada):
    conta_id: int = Field(gt=0)
    valor: ValorPositivo
    descricao: Descricao


class SaqueIn(DepositoIn):
    pass


class TransferenciaIn(Entrada):
    conta_origem_id: int = Field(gt=0)
    conta_destino_id: int = Field(gt=0)
    valor: ValorPositivo
    descricao: Descricao


class EstornoIn(Entrada):
    motivo: Descricao


class TransacaoOut(Saida):
    id: int
    conta_id: int
    conta_destino_id: int | None
    tipo: TipoTransacao
    valor: Dinheiro
    data: datetime
    estado: EstadoTransacao
    descricao: str | None
    transacao_original_id: int | None


class TarifaOut(Saida):
    id: int
    conta_id: int
    tipo: TipoTarifa
    valor: Dinheiro
    estado: EstadoTarifa
    categoria_cliente: CategoriaCliente
    competencia: str
    transacao_id: int | None
    criado_em: datetime
    cobrado_em: datetime | None


class OperacaoOut(BaseModel):
    transacao: TransacaoOut
    tarifa: TarifaOut | None = None
    saldo_conta: Dinheiro


class LancamentoExtrato(TransacaoOut):
    natureza: Literal["credito", "debito"]


class ExtratoOut(BaseModel):
    conta_id: int
    numero: str
    saldo_atual: Dinheiro
    data_inicio: date | None
    data_fim: date | None
    total_creditos: Dinheiro
    total_debitos: Dinheiro
    lancamentos: list[LancamentoExtrato]


# ---------- faturas ----------
class FaturaCreate(Entrada):
    mes_referencia: MesReferencia
    valor: ValorPositivo
    data_vencimento: date


class PagamentoIn(Entrada):
    valor: ValorPositivo


class FaturaOut(Saida):
    id: int
    cartao_id: int
    mes_referencia: str
    valor_original: Dinheiro
    juros: Dinheiro
    valor: Dinheiro
    data_vencimento: date
    estado: EstadoFatura
    data_pagamento: datetime | None
    valor_pago: Dinheiro | None


# ---------- relatorios ----------
class MovimentacaoClienteOut(BaseModel):
    cliente_id: int
    nome: str
    cpf: str
    categoria: CategoriaCliente
    quantidade_transacoes: int
    total_movimentado: Dinheiro


class ContaNegativaOut(BaseModel):
    conta_id: int
    numero: str
    cliente_id: int
    cliente_nome: str
    categoria: CategoriaCliente
    saldo: Dinheiro
    limite_credito: Dinheiro
    estado: EstadoConta
    negativo_desde: datetime | None
    dias_negativo: int


class ReceitaCategoriaOut(BaseModel):
    categoria: CategoriaCliente
    quantidade_tarifas: int
    receita: Dinheiro


class ReceitaTarifasOut(BaseModel):
    data_inicio: date
    data_fim: date
    total: Dinheiro
    por_categoria: list[ReceitaCategoriaOut]


# ---------- rotinas ----------
class RotinaDiariaOut(BaseModel):
    data_referencia: datetime
    faturas_atrasadas: int
    cartoes_bloqueados_por_atraso: int
    clientes_bloqueados_por_saldo_negativo: int


class RotinaTarifasOut(BaseModel):
    competencia: str
    tarifas_geradas: int
    cobradas: int
    pendentes: int
    isentas: int
