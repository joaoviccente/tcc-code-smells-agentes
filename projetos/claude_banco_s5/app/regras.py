"""Parametros de negocio por categoria de cliente.

Os valores abaixo sao exatamente os definidos na especificacao.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.enums import CategoriaCliente


@dataclass(frozen=True)
class RegraCategoria:
    limite_diario_saque: Decimal
    limite_por_transferencia: Decimal
    tarifa_mensal: Decimal
    transacoes_isentas_mes: Optional[int]  # None = ilimitadas
    juros_atraso_mensal: Decimal  # fracao (0.08 = 8% ao mes)


REGRAS: dict[CategoriaCliente, RegraCategoria] = {
    CategoriaCliente.COMUM: RegraCategoria(
        limite_diario_saque=Decimal("1000.00"),
        limite_por_transferencia=Decimal("5000.00"),
        tarifa_mensal=Decimal("30.00"),
        transacoes_isentas_mes=3,
        juros_atraso_mensal=Decimal("0.08"),
    ),
    CategoriaCliente.PREMIUM: RegraCategoria(
        limite_diario_saque=Decimal("5000.00"),
        limite_por_transferencia=Decimal("50000.00"),
        tarifa_mensal=Decimal("0.00"),
        transacoes_isentas_mes=None,
        juros_atraso_mensal=Decimal("0.05"),
    ),
    CategoriaCliente.EMPRESARIAL: RegraCategoria(
        limite_diario_saque=Decimal("20000.00"),
        limite_por_transferencia=Decimal("200000.00"),
        tarifa_mensal=Decimal("120.00"),
        transacoes_isentas_mes=50,
        juros_atraso_mensal=Decimal("0.03"),
    ),
}

# A especificacao nao define o valor da tarifa cobrada por transacao apos
# esgotada a franquia; valor adotado (configuravel aqui).
TARIFA_POR_TRANSACAO = Decimal("5.00")

# Prazos (regras 4, 5 e 6)
PRAZO_ESTORNO_HORAS = 24
DIAS_ATRASO_BLOQUEIO_CARTAO = 10
DIAS_SALDO_NEGATIVO_BLOQUEIO = 30

# Dia de vencimento padrao da fatura (no mes seguinte ao de referencia)
DIA_VENCIMENTO_PADRAO = 10


def regra(categoria: CategoriaCliente) -> RegraCategoria:
    return REGRAS[CategoriaCliente(categoria)]
