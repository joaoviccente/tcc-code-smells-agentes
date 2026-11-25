"""Parametros numericos das regras de negocio (valores exatos da especificacao)."""
from dataclasses import dataclass
from datetime import timedelta
from enum import IntEnum

from app.models import CategoriaAluno


class Prioridade(IntEnum):
    # menor valor = atendido primeiro na lista de espera
    ALTA = 1
    MEDIA = 2
    BAIXA = 3


@dataclass(frozen=True)
class RegraCategoria:
    max_creditos_semestre: int
    max_trancamentos_por_disciplina: int
    prazo_cancelamento_dias: int
    prioridade_espera: Prioridade


REGRAS_CATEGORIA = {
    CategoriaAluno.graduacao: RegraCategoria(28, 2, 15, Prioridade.MEDIA),
    CategoriaAluno.pos: RegraCategoria(16, 1, 30, Prioridade.ALTA),
    CategoriaAluno.especial: RegraCategoria(8, 0, 7, Prioridade.BAIXA),
}

PRAZO_CONFIRMACAO_LISTA_ESPERA = timedelta(hours=48)
MAX_REPROVACOES_DISCIPLINA = 3          # na 3a reprovacao o aluno fica impedido
MIN_CONFIRMADAS_TURMA = 5               # abaixo disso a turma e cancelada
MAX_TRANCAMENTOS_SEMESTRE = 3           # ao atingir, aluno passa a "trancado"
