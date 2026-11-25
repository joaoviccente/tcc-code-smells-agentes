"""Parametros de negocio por categoria de cliente."""
import os
from dataclasses import dataclass
from decimal import Decimal

from app.models import CategoriaCliente


@dataclass(frozen=True)
class RegraCategoria:
    limite_saque_diario: Decimal
    limite_por_transferencia: Decimal
    tarifa_mensal: Decimal
    transacoes_isentas_mes: int | None  # None = ilimitadas
    juros_atraso_mensal: Decimal  # fracao (0.08 = 8% ao mes)


REGRAS: dict[CategoriaCliente, RegraCategoria] = {
    CategoriaCliente.COMUM: RegraCategoria(
        limite_saque_diario=Decimal("1000.00"),
        limite_por_transferencia=Decimal("5000.00"),
        tarifa_mensal=Decimal("30.00"),
        transacoes_isentas_mes=3,
        juros_atraso_mensal=Decimal("0.08"),
    ),
    CategoriaCliente.PREMIUM: RegraCategoria(
        limite_saque_diario=Decimal("5000.00"),
        limite_por_transferencia=Decimal("50000.00"),
        tarifa_mensal=Decimal("0.00"),
        transacoes_isentas_mes=None,
        juros_atraso_mensal=Decimal("0.05"),
    ),
    CategoriaCliente.EMPRESARIAL: RegraCategoria(
        limite_saque_diario=Decimal("20000.00"),
        limite_por_transferencia=Decimal("200000.00"),
        tarifa_mensal=Decimal("120.00"),
        transacoes_isentas_mes=50,
        juros_atraso_mensal=Decimal("0.03"),
    ),
}

# O enunciado nao fixa o valor da tarifa por transacao excedente a franquia;
# fica parametrizavel via variavel de ambiente.
TARIFA_POR_TRANSACAO = Decimal(os.getenv("TARIFA_POR_TRANSACAO", "2.50"))

PRAZO_ESTORNO_HORAS = 24
DIAS_ATRASO_BLOQUEIO_CARTAO = 10
DIAS_NEGATIVO_BLOQUEIO_CLIENTE = 30
DIAS_POR_MES_JUROS = 30


def regra_de(categoria: CategoriaCliente) -> RegraCategoria:
    return REGRAS[CategoriaCliente(categoria)]
