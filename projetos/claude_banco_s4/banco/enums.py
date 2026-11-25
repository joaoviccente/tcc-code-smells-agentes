from enum import Enum


class Categoria(str, Enum):
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


class MotivoBloqueioCartao(str, Enum):
    MANUAL = "manual"
    FATURA_ATRASADA = "fatura_atrasada"
    CLIENTE_BLOQUEADO = "cliente_bloqueado"


class EstadoFatura(str, Enum):
    ABERTA = "aberta"
    FECHADA = "fechada"
    PAGA = "paga"
    ATRASADA = "atrasada"


class TipoTarifa(str, Enum):
    MENSAL = "mensal"
    TRANSACAO = "transacao"
    TRANSFERENCIA_MESMO_TITULAR = "transferencia_mesmo_titular"


class EstadoTarifa(str, Enum):
    PENDENTE = "pendente"
    COBRADA = "cobrada"
    ISENTA = "isenta"
