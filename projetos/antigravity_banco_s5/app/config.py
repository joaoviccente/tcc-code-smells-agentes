from decimal import Decimal
from enum import Enum
from typing import Dict, Any


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
    TRANSFERENCIA_EXCEDENTE = "transferencia_excedente"


class EstadoTarifa(str, Enum):
    PENDENTE = "pendente"
    COBRADA = "cobrada"
    ISENTA = "isenta"


# Regras exatas por categoria de cliente
REGRAS_CATEGORIA: Dict[CategoriaCliente, Dict[str, Any]] = {
    CategoriaCliente.COMUM: {
        "limite_diario_saque": Decimal("1000.00"),
        "limite_por_transferencia": Decimal("5000.00"),
        "tarifa_mensal": Decimal("30.00"),
        "transacoes_isentas_mes": 3,
        "taxa_juros_mensal": Decimal("0.08"),  # 8% ao mês
    },
    CategoriaCliente.PREMIUM: {
        "limite_diario_saque": Decimal("5000.00"),
        "limite_por_transferencia": Decimal("50000.00"),
        "tarifa_mensal": Decimal("0.00"),
        "transacoes_isentas_mes": None,  # Ilimitadas
        "taxa_juros_mensal": Decimal("0.05"),  # 5% ao mês
    },
    CategoriaCliente.EMPRESARIAL: {
        "limite_diario_saque": Decimal("20000.00"),
        "limite_por_transferencia": Decimal("200000.00"),
        "tarifa_mensal": Decimal("120.00"),
        "transacoes_isentas_mes": 50,
        "taxa_juros_mensal": Decimal("0.03"),  # 3% ao mês
    },
}

# Tarifa padrão cobrada por transferência após esgotada a franquia
VALOR_TARIFA_TRANSFERENCIA = Decimal("10.00")

# Constantes de regras de negócio
DIAS_BLOQUEIO_CARTAO_FATURA_ATRASADA = 10
DIAS_BLOQUEIO_CONTA_SALDO_NEGATIVO = 30
HORAS_LIMITE_ESTORNO = 24
DATABASE_URL = "sqlite:///./banco.db"
