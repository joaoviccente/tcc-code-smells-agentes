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

# Category rules constants
REGRAS_CATEGORIA = {
    CategoriaAluno.GRADUACAO: {
        "max_creditos": 28,
        "max_trancamentos": 2,
        "prazo_cancelamento_dias": 15,
        "prioridade_espera": 2,  # média
    },
    CategoriaAluno.POS: {
        "max_creditos": 16,
        "max_trancamentos": 1,
        "prazo_cancelamento_dias": 30,
        "prioridade_espera": 3,  # alta
    },
    CategoriaAluno.ESPECIAL: {
        "max_creditos": 8,
        "max_trancamentos": 0,
        "prazo_cancelamento_dias": 7,
        "prioridade_espera": 1,  # baixa
    },
}
