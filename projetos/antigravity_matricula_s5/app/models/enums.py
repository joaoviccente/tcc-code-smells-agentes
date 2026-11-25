import enum

class CategoriaAluno(str, enum.Enum):
    GRADUACAO = "graduacao"
    POS = "pos"
    ESPECIAL = "especial"

    @property
    def prioridade_fila(self) -> int:
        """
        Retorna o ranking de prioridade na lista de espera.
        Menor número indica maior prioridade.
        Pos: alta (1)
        Graduacao: media (2)
        Especial: baixa (3)
        """
        prioridades = {
            CategoriaAluno.POS: 1,
            CategoriaAluno.GRADUACAO: 2,
            CategoriaAluno.ESPECIAL: 3
        }
        return prioridades[self]

    @property
    def max_creditos(self) -> int:
        from app.config import settings
        limites = {
            CategoriaAluno.GRADUACAO: settings.MAX_CREDITOS_GRADUACAO,
            CategoriaAluno.POS: settings.MAX_CREDITOS_POS,
            CategoriaAluno.ESPECIAL: settings.MAX_CREDITOS_ESPECIAL
        }
        return limites[self]

    @property
    def max_trancamentos(self) -> int:
        from app.config import settings
        limites = {
            CategoriaAluno.GRADUACAO: settings.MAX_TRANCAMENTOS_GRADUACAO,
            CategoriaAluno.POS: settings.MAX_TRANCAMENTOS_POS,
            CategoriaAluno.ESPECIAL: settings.MAX_TRANCAMENTOS_ESPECIAL
        }
        return limites[self]

    @property
    def prazo_cancelamento_dias(self) -> int:
        from app.config import settings
        prazos = {
            CategoriaAluno.GRADUACAO: settings.PRAZO_CANCELAMENTO_GRADUACAO_DIAS,
            CategoriaAluno.POS: settings.PRAZO_CANCELAMENTO_POS_DIAS,
            CategoriaAluno.ESPECIAL: settings.PRAZO_CANCELAMENTO_ESPECIAL_DIAS
        }
        return prazos[self]


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
    REPROVADO_POR_FALTA = "reprovado_por_falta"
    TRANCADO = "trancado"
