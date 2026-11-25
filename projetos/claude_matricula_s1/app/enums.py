from enum import Enum


class CategoriaAluno(str, Enum):
    GRADUACAO = "graduacao"
    POS = "pos"
    ESPECIAL = "especial"


class SituacaoAluno(str, Enum):
    ATIVO = "ativo"
    TRANCADO = "trancado"
    JUBILADO = "jubilado"


class EstadoTurma(str, Enum):
    ABERTA = "aberta"
    LOTADA = "lotada"
    CANCELADA = "cancelada"
    ENCERRADA = "encerrada"


class EstadoMatricula(str, Enum):
    SOLICITADA = "solicitada"
    CONFIRMADA = "confirmada"
    LISTA_DE_ESPERA = "lista_de_espera"
    CANCELADA = "cancelada"
    TRANCADA = "trancada"


class SituacaoHistorico(str, Enum):
    APROVADO = "aprovado"
    REPROVADO = "reprovado"
    TRANCADO = "trancado"


class DiaSemana(str, Enum):
    SEG = "SEG"
    TER = "TER"
    QUA = "QUA"
    QUI = "QUI"
    SEX = "SEX"
    SAB = "SAB"
    DOM = "DOM"
