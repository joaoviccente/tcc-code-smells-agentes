"""Parametros numericos das regras de negocio. Valores definidos pela especificacao."""
from dataclasses import dataclass
from datetime import timedelta

from app.models import Categoria


@dataclass(frozen=True)
class RegraCategoria:
    max_creditos_semestre: int
    max_trancamentos_por_disciplina: int
    prazo_cancelamento_dias: int
    prioridade_fila: int  # menor valor = atendido primeiro
    prioridade_nome: str


REGRAS: dict[Categoria, RegraCategoria] = {
    Categoria.GRADUACAO: RegraCategoria(28, 2, 15, 2, "media"),
    Categoria.POS: RegraCategoria(16, 1, 30, 1, "alta"),
    Categoria.ESPECIAL: RegraCategoria(8, 0, 7, 3, "baixa"),
}

PRAZO_CONFIRMACAO_FILA = timedelta(hours=48)
MAX_REPROVACOES_DISCIPLINA = 3
MIN_CONFIRMADAS_TURMA = 5
MAX_TRANCAMENTOS_SEMESTRE = 3
