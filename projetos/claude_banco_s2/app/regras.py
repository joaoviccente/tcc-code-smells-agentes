"""Parametros de negocio por categoria de cliente (valores exatos da especificacao)."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from app.models import CategoriaCliente


@dataclass(frozen=True)
class RegrasCategoria:
    limite_saque_diario: Decimal
    limite_por_transferencia: Decimal
    tarifa_mensal: Decimal
    transacoes_isentas_mes: int | None  # None = ilimitadas
    juros_atraso_mensal: Decimal  # fracao (0.08 = 8% ao mes)


REGRAS: dict[CategoriaCliente, RegrasCategoria] = {
    CategoriaCliente.COMUM: RegrasCategoria(
        limite_saque_diario=Decimal("1000.00"),
        limite_por_transferencia=Decimal("5000.00"),
        tarifa_mensal=Decimal("30.00"),
        transacoes_isentas_mes=3,
        juros_atraso_mensal=Decimal("0.08"),
    ),
    CategoriaCliente.PREMIUM: RegrasCategoria(
        limite_saque_diario=Decimal("5000.00"),
        limite_por_transferencia=Decimal("50000.00"),
        tarifa_mensal=Decimal("0.00"),
        transacoes_isentas_mes=None,
        juros_atraso_mensal=Decimal("0.05"),
    ),
    CategoriaCliente.EMPRESARIAL: RegrasCategoria(
        limite_saque_diario=Decimal("20000.00"),
        limite_por_transferencia=Decimal("200000.00"),
        tarifa_mensal=Decimal("120.00"),
        transacoes_isentas_mes=50,
        juros_atraso_mensal=Decimal("0.03"),
    ),
}

PRAZO_ESTORNO = timedelta(hours=24)
DIAS_ATRASO_BLOQUEIO_CARTAO = 10
DIAS_SALDO_NEGATIVO_BLOQUEIO = 30
