"""Enumerações utilizadas nas entidades do sistema acadêmico."""

import enum


class CategoriaAluno(str, enum.Enum):
    GRADUACAO = "graduacao"
    POS = "pos"
    ESPECIAL = "especial"


class SituacaoAluno(str, enum.Enum):
    ATIVO = "ativo"
    TRANCADO = "trancado"
    JUBILADO = "jubilado"


class EstadoTurma(str, enum.Enum):
    ABERTA = "aberta"
    LOTADA = "lotada"
    CANCELADA = "cancelada"
    ENCERRADA = "encerrada"


class EstadoMatricula(str, enum.Enum):
    SOLICITADA = "solicitada"
    CONFIRMADA = "confirmada"
    LISTA_DE_ESPERA = "lista_de_espera"
    CANCELADA = "cancelada"
    TRANCADA = "trancada"


class SituacaoHistorico(str, enum.Enum):
    APROVADO = "aprovado"
    REPROVADO = "reprovado"
    TRANCADO = "trancado"
    REPROVADO_POR_FALTA = "reprovado_por_falta"
