import os
from decimal import Decimal
from enum import Enum


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


class TipoTarifa(str, Enum):
    MENSALIDADE = "mensalidade"
    TRANSFERENCIA = "transferencia"
    SAQUE = "saque"
    OUTRO = "outro"


class EstadoTarifa(str, Enum):
    PENDENTE = "pendente"
    COBRADA = "cobrada"
    ISENTA = "isenta"


# REGRAS POR CATEGORIA DE CLIENTE
# Comum: limite diário de saque R$ 1.000,00; limite por transferência R$ 5.000,00;
#        tarifa mensal R$ 30,00; 3 transações isentas por mês; juros de atraso 8% ao mês.
# Premium: limite diário de saque R$ 5.000,00; limite por transferência R$ 50.000,00;
#          sem tarifa mensal; transações isentas ilimitadas; juros de atraso 5% ao mês.
# Empresarial: limite diário de saque R$ 20.000,00; limite por transferência R$ 200.000,00;
#              tarifa mensal R$ 120,00; 50 transações isentas por mês; juros de atraso 3% ao mês.

REGRAS_CATEGORIA = {
    CategoriaCliente.COMUM: {
        "limite_diario_saque": Decimal("1000.00"),
        "limite_por_transferencia": Decimal("5000.00"),
        "tarifa_mensal": Decimal("30.00"),
        "transacoes_isentas_mes": 3,
        "juros_atraso_mes": Decimal("0.08"),  # 8% ao mês
    },
    CategoriaCliente.PREMIUM: {
        "limite_diario_saque": Decimal("5000.00"),
        "limite_por_transferencia": Decimal("50000.00"),
        "tarifa_mensal": Decimal("0.00"),
        "transacoes_isentas_mes": None,  # Ilimitadas
        "juros_atraso_mes": Decimal("0.05"),  # 5% ao mês
    },
    CategoriaCliente.EMPRESARIAL: {
        "limite_diario_saque": Decimal("20000.00"),
        "limite_por_transferencia": Decimal("200000.00"),
        "tarifa_mensal": Decimal("120.00"),
        "transacoes_isentas_mes": 50,
        "juros_atraso_mes": Decimal("0.03"),  # 3% ao mês
    },
}

# Tarifa padrão cobrada em transferências quando a franquia mensal é esgotada
VALOR_TARIFA_TRANSFERENCIA_EXCEDENTE = Decimal("10.00")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banco.db")
