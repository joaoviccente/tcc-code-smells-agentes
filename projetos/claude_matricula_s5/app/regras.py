"""Parametros numericos das regras de negocio (valores definidos na especificacao)."""

from dataclasses import dataclass
from datetime import timedelta

from .enums import CategoriaAluno

PESO_PRIORIDADE = {"alta": 3, "media": 2, "baixa": 1}


@dataclass(frozen=True)
class RegraCategoria:
    max_creditos_semestre: int
    max_trancamentos_por_disciplina: int
    prazo_cancelamento_dias: int
    prioridade_lista_espera: str  # "alta" | "media" | "baixa"

    @property
    def peso_prioridade(self) -> int:
        return PESO_PRIORIDADE[self.prioridade_lista_espera]


REGRAS_CATEGORIA: dict[CategoriaAluno, RegraCategoria] = {
    CategoriaAluno.GRADUACAO: RegraCategoria(
        max_creditos_semestre=28,
        max_trancamentos_por_disciplina=2,
        prazo_cancelamento_dias=15,
        prioridade_lista_espera="media",
    ),
    CategoriaAluno.POS: RegraCategoria(
        max_creditos_semestre=16,
        max_trancamentos_por_disciplina=1,
        prazo_cancelamento_dias=30,
        prioridade_lista_espera="alta",
    ),
    CategoriaAluno.ESPECIAL: RegraCategoria(
        max_creditos_semestre=8,
        max_trancamentos_por_disciplina=0,
        prazo_cancelamento_dias=7,
        prioridade_lista_espera="baixa",
    ),
}

# Regra 2: prazo para o primeiro da fila confirmar a vaga liberada.
PRAZO_CONFIRMACAO_LISTA_ESPERA = timedelta(hours=48)
# Regra 3: numero de reprovacoes na mesma disciplina que impede nova matricula.
LIMITE_REPROVACOES_DISCIPLINA = 3
# Regra 5: minimo de matriculas confirmadas para a turma nao ser cancelada.
MIN_MATRICULAS_CONFIRMADAS_TURMA = 5
# Regra 7: numero de trancamentos no semestre que leva o aluno a situacao "trancado".
LIMITE_TRANCAMENTOS_SEMESTRE = 3
