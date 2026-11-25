import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_validator

from .enums import (
    Categoria,
    EstadoCartao,
    EstadoConta,
    EstadoFatura,
    EstadoTarifa,
    EstadoTransacao,
    MotivoBloqueioCartao,
    SituacaoCliente,
    TipoConta,
    TipoTarifa,
    TipoTransacao,
)

# Entrada: valores monetarios positivos com no maximo 2 casas decimais.
ValorPositivo = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=2)]
ValorNaoNegativo = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=2)]
# Saida: serializa Decimal como numero JSON.
DinheiroOut = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- Cliente
def validar_cpf(valor: str) -> str:
    cpf = re.sub(r"\D", "", valor or "")
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        raise ValueError("CPF invalido")
    for n in (9, 10):
        soma = sum(int(cpf[i]) * (n + 1 - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(cpf[n]):
            raise ValueError("CPF invalido")
    return cpf


Nome = Annotated[str, Field(min_length=2, max_length=150)]


class ClienteCreate(Entrada):
    nome: Nome
    cpf: str
    email: EmailStr
    categoria: Categoria

    @field_validator("cpf")
    @classmethod
    def _cpf(cls, v: str) -> str:
        return validar_cpf(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.lower()


class ClienteUpdate(Entrada):
    nome: Nome | None = None
    email: EmailStr | None = None
    categoria: Categoria | None = None
    situacao: SituacaoCliente | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        return v.lower() if v else v


class ClienteOut(Saida):
    id: int
    nome: str
    cpf: str
    email: str
    categoria: Categoria
    situacao: SituacaoCliente
    criado_em: datetime


# ---------------------------------------------------------------- Conta
class ContaCreate(Entrada):
    cliente_id: int = Field(gt=0)
    tipo: TipoConta
    limite_credito: ValorNaoNegativo = Decimal("0.00")


class ContaUpdate(Entrada):
    limite_credito: ValorNaoNegativo | None = None
    estado: EstadoConta | None = None


class ContaOut(Saida):
    id: int
    numero: str
    cliente_id: int
    tipo: TipoConta
    saldo: DinheiroOut
    limite_credito: DinheiroOut
    estado: EstadoConta
    negativo_desde: datetime | None
    criado_em: datetime
    encerrada_em: datetime | None


# ---------------------------------------------------------------- Cartao
class CartaoCreate(Entrada):
    conta_id: int = Field(gt=0)
    limite: ValorPositivo


class CartaoUpdate(Entrada):
    limite: ValorPositivo | None = None
    estado: EstadoCartao | None = None


class CartaoOut(Saida):
    id: int
    conta_id: int
    numero: str
    limite: DinheiroOut
    estado: EstadoCartao
    motivo_bloqueio: MotivoBloqueioCartao | None
    criado_em: datetime


class CompraCartao(Entrada):
    valor: ValorPositivo
    descricao: str | None = Field(default=None, max_length=255)


# ---------------------------------------------------------------- Transacoes
class Deposito(Entrada):
    conta_id: int = Field(gt=0)
    valor: ValorPositivo
    descricao: str | None = Field(default=None, max_length=255)


class Saque(Deposito):
    pass


class Transferencia(Entrada):
    conta_origem_id: int = Field(gt=0)
    conta_destino_id: int = Field(gt=0)
    valor: ValorPositivo
    descricao: str | None = Field(default=None, max_length=255)


class TransacaoOut(Saida):
    id: int
    conta_id: int
    conta_destino_id: int | None
    tipo: TipoTransacao
    valor: DinheiroOut
    data: datetime
    estado: EstadoTransacao
    transacao_original_id: int | None
    descricao: str | None


class TarifaOut(Saida):
    id: int
    conta_id: int
    tipo: TipoTarifa
    valor: DinheiroOut
    estado: EstadoTarifa
    competencia: str
    data: datetime
    data_cobranca: datetime | None
    transacao_id: int | None
    descricao: str | None


class OperacaoOut(BaseModel):
    transacao: TransacaoOut
    tarifa: TarifaOut | None = None
    saldos: dict[int, DinheiroOut]


class ItemExtrato(BaseModel):
    transacao: TransacaoOut
    efeito: DinheiroOut  # credito (+) ou debito (-) na conta do extrato


class ExtratoOut(BaseModel):
    conta_id: int
    numero: str
    saldo_atual: DinheiroOut
    limite_credito: DinheiroOut
    inicio: datetime | None
    fim: datetime | None
    itens: list[ItemExtrato]


# ---------------------------------------------------------------- Faturas
class FaturaOut(Saida):
    id: int
    cartao_id: int
    mes_referencia: str
    valor: DinheiroOut
    juros: DinheiroOut
    valor_total: DinheiroOut
    vencimento: date
    estado: EstadoFatura
    data_pagamento: datetime | None
    valor_pago: DinheiroOut | None


class PagamentoFatura(Entrada):
    valor: ValorPositivo


# ---------------------------------------------------------------- Relatorios / rotinas
class MovimentacaoCliente(BaseModel):
    cliente_id: int
    nome: str
    categoria: Categoria
    quantidade_transacoes: int
    total_movimentado: DinheiroOut


class ContaNegativa(BaseModel):
    conta_id: int
    numero: str
    cliente_id: int
    nome_cliente: str
    saldo: DinheiroOut
    limite_credito: DinheiroOut
    negativo_desde: datetime | None
    dias_negativo: int


class ReceitaCategoria(BaseModel):
    categoria: Categoria
    quantidade_tarifas: int
    receita: DinheiroOut


class ResultadoRotina(BaseModel):
    data_referencia: date
    faturas_fechadas: int
    faturas_atrasadas: int
    cartoes_bloqueados_por_atraso: int
    clientes_bloqueados_por_saldo_negativo: int
    cartoes_bloqueados_por_cliente: int
    tarifas_mensais_geradas: int
    tarifas_pendentes_cobradas: int
