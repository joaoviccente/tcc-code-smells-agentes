import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field

from app.enums import (
    CategoriaCliente, EstadoCartao, EstadoConta, EstadoFatura, EstadoTarifa,
    EstadoTransacao, SituacaoCliente, TipoConta, TipoTarifa, TipoTransacao,
)

# ---------------------------------------------------------------- tipos base

def _duas_casas(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"))


ValorPositivo = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=2,
                                         examples=["100.00"]), AfterValidator(_duas_casas)]
ValorNaoNegativo = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=2,
                                            examples=["0.00"]), AfterValidator(_duas_casas)]

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
_MES_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def validar_cpf(valor: str) -> str:
    cpf = re.sub(r"[.\-\s]", "", valor or "")
    if not re.fullmatch(r"\d{11}", cpf):
        raise ValueError("CPF deve conter 11 digitos")
    if cpf == cpf[0] * 11:
        raise ValueError("CPF invalido")
    for n in (9, 10):
        soma = sum(int(cpf[i]) * (n + 1 - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(cpf[n]):
            raise ValueError("CPF invalido (digito verificador)")
    return cpf


def validar_email(valor: str) -> str:
    v = (valor or "").strip().lower()
    if len(v) > 254 or not _EMAIL_RE.fullmatch(v):
        raise ValueError("e-mail invalido")
    return v


def validar_nome(valor: str) -> str:
    v = " ".join((valor or "").split())
    if len(v) < 2:
        raise ValueError("nome deve ter ao menos 2 caracteres")
    return v


def validar_mes(valor: str) -> str:
    if not _MES_RE.fullmatch(valor or ""):
        raise ValueError("mes de referencia deve estar no formato AAAA-MM")
    return valor


CPF = Annotated[str, AfterValidator(validar_cpf)]
Email = Annotated[str, AfterValidator(validar_email)]
Nome = Annotated[str, Field(max_length=120), AfterValidator(validar_nome)]
MesReferencia = Annotated[str, AfterValidator(validar_mes), Field(examples=["2026-11"])]
Descricao = Annotated[Optional[str], Field(default=None, max_length=200)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ clientes

class ClienteCriar(Entrada):
    nome: Nome
    cpf: CPF
    email: Email
    categoria: CategoriaCliente
    situacao: SituacaoCliente = SituacaoCliente.ATIVO


class ClienteAtualizar(Entrada):
    nome: Optional[Nome] = None
    email: Optional[Email] = None
    categoria: Optional[CategoriaCliente] = None
    situacao: Optional[SituacaoCliente] = None


class ClienteOut(Saida):
    id: int
    nome: str
    cpf: str
    email: str
    categoria: CategoriaCliente
    situacao: SituacaoCliente
    criado_em: datetime


# -------------------------------------------------------------------- contas

class ContaCriar(Entrada):
    cliente_id: int = Field(gt=0)
    tipo: TipoConta
    limite_credito: ValorNaoNegativo = Decimal("0.00")


class ContaAtualizar(Entrada):
    limite_credito: Optional[ValorNaoNegativo] = None
    estado: Optional[Literal["ativa", "bloqueada"]] = None


class ContaOut(Saida):
    id: int
    numero: str
    cliente_id: int
    tipo: TipoConta
    saldo: Decimal
    limite_credito: Decimal
    estado: EstadoConta
    negativo_desde: Optional[datetime]
    criada_em: datetime
    encerrada_em: Optional[datetime]


# ------------------------------------------------------------------- cartoes

class CartaoCriar(Entrada):
    conta_id: int = Field(gt=0)
    limite: ValorPositivo


class CartaoAtualizar(Entrada):
    limite: Optional[ValorPositivo] = None
    estado: Optional[Literal["ativo", "bloqueado"]] = None


class CartaoOut(Saida):
    id: int
    numero: str
    conta_id: int
    limite: Decimal
    estado: EstadoCartao
    criado_em: datetime


# ---------------------------------------------------------------- transacoes

class DepositoIn(Entrada):
    conta_id: int = Field(gt=0)
    valor: ValorPositivo
    descricao: Descricao = None


class SaqueIn(Entrada):
    conta_id: int = Field(gt=0)
    valor: ValorPositivo
    descricao: Descricao = None


class TransferenciaIn(Entrada):
    conta_origem_id: int = Field(gt=0)
    conta_destino_id: int = Field(gt=0)
    valor: ValorPositivo
    descricao: Descricao = None


class EstornoIn(Entrada):
    descricao: Descricao = None


class TarifaOut(Saida):
    id: int
    conta_id: int
    tipo: TipoTarifa
    valor: Decimal
    estado: EstadoTarifa
    mes_referencia: str
    categoria_cliente: CategoriaCliente
    transacao_id: Optional[int]
    criada_em: datetime
    cobrada_em: Optional[datetime]


class TransacaoOut(Saida):
    id: int
    conta_id: int
    conta_destino_id: Optional[int]
    tipo: TipoTransacao
    valor: Decimal
    data: datetime
    estado: EstadoTransacao
    descricao: Optional[str]
    transacao_original_id: Optional[int]


class OperacaoOut(BaseModel):
    transacao: TransacaoOut
    tarifa: Optional[TarifaOut] = None
    saldo_conta: Decimal


class EstornoOut(BaseModel):
    estorno: TransacaoOut
    transacao_original: TransacaoOut


class LancamentoExtrato(BaseModel):
    transacao_id: int
    data: datetime
    tipo: TipoTransacao
    estado: EstadoTransacao
    descricao: Optional[str]
    natureza: Literal["credito", "debito"]
    valor: Decimal
    conta_contraparte_id: Optional[int]
    transacao_original_id: Optional[int]


class ExtratoOut(BaseModel):
    conta_id: int
    numero: str
    saldo_atual: Decimal
    inicio: Optional[datetime]
    fim: Optional[datetime]
    lancamentos: list[LancamentoExtrato]
    tarifas_cobradas: list[TarifaOut]


# ------------------------------------------------------------------- faturas

class FaturaCriar(Entrada):
    mes_referencia: MesReferencia
    valor: ValorPositivo
    data_vencimento: Optional[date] = None


class PagamentoFaturaIn(Entrada):
    valor: ValorPositivo


class FaturaOut(Saida):
    id: int
    cartao_id: int
    mes_referencia: str
    valor: Decimal
    juros: Decimal
    data_vencimento: date
    estado: EstadoFatura
    data_pagamento: Optional[datetime]
    valor_pago: Optional[Decimal]

    @computed_field
    @property
    def valor_total(self) -> Decimal:
        return self.valor + self.juros


# ---------------------------------------------------------------- relatorios

class ClienteMovimentacao(BaseModel):
    cliente_id: int
    nome: str
    categoria: CategoriaCliente
    quantidade_transacoes: int
    total_movimentado: Decimal


class ContaNegativa(BaseModel):
    conta_id: int
    numero: str
    cliente_id: int
    cliente_nome: str
    categoria: CategoriaCliente
    estado: EstadoConta
    saldo: Decimal
    limite_credito: Decimal
    negativo_desde: Optional[datetime]
    dias_negativo: int


class ReceitaCategoria(BaseModel):
    categoria: CategoriaCliente
    quantidade_tarifas_cobradas: int
    receita_mensalidades: Decimal
    receita_transacoes: Decimal
    receita_total: Decimal
    valor_pendente: Decimal


class ReceitaTarifasOut(BaseModel):
    inicio: Optional[datetime]
    fim: Optional[datetime]
    categorias: list[ReceitaCategoria]
    receita_total: Decimal


# ------------------------------------------------------------- processamento

class ProcessamentoDiarioOut(BaseModel):
    data_referencia: date
    faturas_marcadas_atrasadas: int
    faturas_com_juros_atualizados: int
    cartoes_bloqueados_por_atraso: int
    clientes_bloqueados_saldo_negativo: int
    cartoes_bloqueados_saldo_negativo: int
    tarifas_pendentes_cobradas: int


class TarifasMensaisIn(Entrada):
    mes_referencia: MesReferencia


class TarifasMensaisOut(BaseModel):
    mes_referencia: str
    geradas: int
    cobradas: int
    isentas: int
    pendentes: int
    ja_existentes: int
