from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
import os


def get_current_time() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CategoriaCliente(str, Enum):
    COMUM = "comum"
    PREMIUM = "premium"
    EMPRESARIAL = "empresarial"


class SituacaoCliente(str, Enum):
    ATIVO = "ativo"
    BLOQUEADO = "bloqueado"


class TipoConta(str, Enum):
    CORRENTE = "corrente"
    POUPANCA = "poupanca"


class EstadoConta(str, Enum):
    ATIVA = "ativa"
    BLOQUEADA = "bloqueada"
    ENCERRADA = "encerrada"


class TipoTransacao(str, Enum):
    DEPOSITO = "deposito"
    SAQUE = "saque"
    TRANSFERENCIA = "transferencia"
    ESTORNO = "estorno"


class EstadoTransacao(str, Enum):
    PENDENTE = "pendente"
    EFETIVADA = "efetivada"
    ESTORNADA = "estornada"


class EstadoCartao(str, Enum):
    ATIVO = "ativo"
    BLOQUEADO = "bloqueado"
    CANCELADO = "cancelado"


class EstadoFatura(str, Enum):
    ABERTA = "aberta"
    FECHADA = "fechada"
    PAGA = "paga"
    ATRASADA = "atrasada"


class EstadoTarifa(str, Enum):
    PENDENTE = "pendente"
    COBRADA = "cobrada"
    ISENTA = "isenta"


class TipoTarifa(str, Enum):
    MANUTENCAO_MENSAL = "manutencao_mensal"
    TRANSFERENCIA_EXCEDENTE = "transferencia_excedente"


@dataclass(frozen=True)
class RegrasCategoria:
    limite_diario_saque: Decimal
    limite_por_transferencia: Decimal
    tarifa_mensal: Decimal
    transacoes_isentas_mes: Optional[int]  # None = ilimitadas
    taxa_juros_atraso_mensal: Decimal      # ex: 0.08 para 8%


REGRAS_CATEGORIAS: dict[CategoriaCliente, RegrasCategoria] = {
    CategoriaCliente.COMUM: RegrasCategoria(
        limite_diario_saque=Decimal("1000.00"),
        limite_por_transferencia=Decimal("5000.00"),
        tarifa_mensal=Decimal("30.00"),
        transacoes_isentas_mes=3,
        taxa_juros_atraso_mensal=Decimal("0.08"),
    ),
    CategoriaCliente.PREMIUM: RegrasCategoria(
        limite_diario_saque=Decimal("5000.00"),
        limite_por_transferencia=Decimal("50000.00"),
        tarifa_mensal=Decimal("0.00"),
        transacoes_isentas_mes=None,  # Ilimitadas
        taxa_juros_atraso_mensal=Decimal("0.05"),
    ),
    CategoriaCliente.EMPRESARIAL: RegrasCategoria(
        limite_diario_saque=Decimal("20000.00"),
        limite_por_transferencia=Decimal("200000.00"),
        tarifa_mensal=Decimal("120.00"),
        transacoes_isentas_mes=50,
        taxa_juros_atraso_mensal=Decimal("0.03"),
    ),
}

# Constantes de regras de negócio
LIMITE_HORAS_ESTORNO = 24
DIAS_BLOQUEIO_CARTAO_FATURA = 10
DIAS_BLOQUEIO_SALDO_NEGATIVO = 30
VALOR_TARIFA_TRANSFERENCIA_PADRAO = Decimal("10.00")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banco.db")
