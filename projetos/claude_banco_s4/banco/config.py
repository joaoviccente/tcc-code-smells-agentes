"""Parametros de negocio. Os valores por categoria seguem exatamente a especificacao."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from .enums import Categoria


@dataclass(frozen=True)
class RegrasCategoria:
    limite_diario_saque: Decimal
    limite_por_transferencia: Decimal
    tarifa_mensal: Decimal
    transacoes_isentas_mes: int | None  # None = ilimitadas
    juros_atraso_mensal: Decimal  # fracao (0.08 = 8% ao mes)


REGRAS: dict[Categoria, RegrasCategoria] = {
    Categoria.COMUM: RegrasCategoria(
        limite_diario_saque=Decimal("1000.00"),
        limite_por_transferencia=Decimal("5000.00"),
        tarifa_mensal=Decimal("30.00"),
        transacoes_isentas_mes=3,
        juros_atraso_mensal=Decimal("0.08"),
    ),
    Categoria.PREMIUM: RegrasCategoria(
        limite_diario_saque=Decimal("5000.00"),
        limite_por_transferencia=Decimal("50000.00"),
        tarifa_mensal=Decimal("0.00"),
        transacoes_isentas_mes=None,
        juros_atraso_mensal=Decimal("0.05"),
    ),
    Categoria.EMPRESARIAL: RegrasCategoria(
        limite_diario_saque=Decimal("20000.00"),
        limite_por_transferencia=Decimal("200000.00"),
        tarifa_mensal=Decimal("120.00"),
        transacoes_isentas_mes=50,
        juros_atraso_mensal=Decimal("0.03"),
    ),
}

# A especificacao nao define o valor da tarifa por transacao excedente a franquia.
# Valor adotado (premissa documentada no README); altere aqui se necessario.
TARIFA_POR_TRANSACAO = Decimal("2.50")

PRAZO_ESTORNO = timedelta(hours=24)
DIAS_ATRASO_BLOQUEIO_CARTAO = 10       # bloqueia apos 10 dias de atraso (> 10)
DIAS_SALDO_NEGATIVO_BLOQUEIO = 30      # bloqueia apos mais de 30 dias negativo (> 30)
DIA_VENCIMENTO_FATURA = 10             # vencimento no dia 10 do mes seguinte a referencia
DIAS_BASE_JUROS = 30                   # juros simples pro rata die (taxa mensal / 30)
