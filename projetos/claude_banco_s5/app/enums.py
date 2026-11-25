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
    MENSAL = "mensal"
    TRANSACAO = "transacao"


class EstadoTarifa(str, Enum):
    PENDENTE = "pendente"
    COBRADA = "cobrada"
    ISENTA = "isenta"
