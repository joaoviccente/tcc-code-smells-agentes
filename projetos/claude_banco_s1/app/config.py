"""Regras parametrizadas por categoria de cliente.

Todos os valores monetarios sao Decimal para garantir exatidao.
"""
import os
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RegraCategoria:
    limite_diario_saque: Decimal
    limite_por_transferencia: Decimal
    tarifa_mensal: Decimal
    transacoes_isentas_mes: int | None  # None = ilimitadas
    juros_atraso_mes: Decimal  # fracao (0.08 = 8% ao mes)


REGRAS: dict[str, RegraCategoria] = {
    "comum": RegraCategoria(
        limite_diario_saque=Decimal("1000.00"),
        limite_por_transferencia=Decimal("5000.00"),
        tarifa_mensal=Decimal("30.00"),
        transacoes_isentas_mes=3,
        juros_atraso_mes=Decimal("0.08"),
    ),
    "premium": RegraCategoria(
        limite_diario_saque=Decimal("5000.00"),
        limite_por_transferencia=Decimal("50000.00"),
        tarifa_mensal=Decimal("0.00"),
        transacoes_isentas_mes=None,
        juros_atraso_mes=Decimal("0.05"),
    ),
    "empresarial": RegraCategoria(
        limite_diario_saque=Decimal("20000.00"),
        limite_por_transferencia=Decimal("200000.00"),
        tarifa_mensal=Decimal("120.00"),
        transacoes_isentas_mes=50,
        juros_atraso_mes=Decimal("0.03"),
    ),
}

# O enunciado nao define o valor da tarifa cobrada por transacao apos esgotada
# a franquia; o valor e configuravel via variavel de ambiente.
TARIFA_POR_TRANSACAO = Decimal(os.getenv("TARIFA_POR_TRANSACAO", "5.00"))

PRAZO_ESTORNO_HORAS = 24
DIAS_ATRASO_BLOQUEIO_CARTAO = 10
DIAS_NEGATIVO_BLOQUEIO_CLIENTE = 30
DIA_VENCIMENTO_FATURA = 10

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banco.db")


def regra(categoria: str) -> RegraCategoria:
    return REGRAS[categoria]
