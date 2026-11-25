"""Parâmetros das regras de negócio (valores definidos na especificação)."""
from dataclasses import dataclass
from datetime import timedelta

from .models import CategoriaAluno


@dataclass(frozen=True)
class RegraCategoria:
    max_creditos_semestre: int
    max_trancamentos_por_disciplina: int
    prazo_cancelamento_dias: int
    prioridade_lista_espera: int  # menor valor = atendido primeiro
    rotulo_prioridade: str


REGRAS_CATEGORIA: dict[CategoriaAluno, RegraCategoria] = {
    CategoriaAluno.graduacao: RegraCategoria(
        max_creditos_semestre=28,
        max_trancamentos_por_disciplina=2,
        prazo_cancelamento_dias=15,
        prioridade_lista_espera=2,
        rotulo_prioridade="media",
    ),
    CategoriaAluno.pos: RegraCategoria(
        max_creditos_semestre=16,
        max_trancamentos_por_disciplina=1,
        prazo_cancelamento_dias=30,
        prioridade_lista_espera=1,
        rotulo_prioridade="alta",
    ),
    CategoriaAluno.especial: RegraCategoria(
        max_creditos_semestre=8,
        max_trancamentos_por_disciplina=0,
        prazo_cancelamento_dias=7,
        prioridade_lista_espera=3,
        rotulo_prioridade="baixa",
    ),
}

# Regra 2: prazo para o primeiro da fila confirmar a vaga liberada.
PRAZO_CONFIRMACAO_LISTA_ESPERA = timedelta(hours=48)
# Regra 3: número de reprovações que impede nova matrícula na disciplina.
MAX_REPROVACOES_POR_DISCIPLINA = 3
# Regra 5: mínimo de matrículas confirmadas para a turma não ser cancelada.
MIN_CONFIRMADAS_POR_TURMA = 5
# Regra 7: trancamentos no semestre que levam o aluno à situação "trancado".
MAX_TRANCAMENTOS_SEMESTRE = 3


def regra_do_aluno(categoria: CategoriaAluno) -> RegraCategoria:
    return REGRAS_CATEGORIA[CategoriaAluno(categoria)]
