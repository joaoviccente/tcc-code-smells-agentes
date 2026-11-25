"""Parametros numericos das regras de negocio (valores exigidos pela especificacao)."""
from dataclasses import dataclass
from datetime import timedelta

from app.enums import CategoriaAluno


@dataclass(frozen=True)
class RegrasCategoria:
    max_creditos_semestre: int
    max_trancamentos_por_disciplina: int
    prazo_cancelamento_dias: int
    prioridade_lista_espera: int  # quanto maior, mais prioritario
    rotulo_prioridade: str


REGRAS_POR_CATEGORIA: dict[CategoriaAluno, RegrasCategoria] = {
    CategoriaAluno.GRADUACAO: RegrasCategoria(
        max_creditos_semestre=28,
        max_trancamentos_por_disciplina=2,
        prazo_cancelamento_dias=15,
        prioridade_lista_espera=2,
        rotulo_prioridade="media",
    ),
    CategoriaAluno.POS: RegrasCategoria(
        max_creditos_semestre=16,
        max_trancamentos_por_disciplina=1,
        prazo_cancelamento_dias=30,
        prioridade_lista_espera=3,
        rotulo_prioridade="alta",
    ),
    CategoriaAluno.ESPECIAL: RegrasCategoria(
        max_creditos_semestre=8,
        max_trancamentos_por_disciplina=0,
        prazo_cancelamento_dias=7,
        prioridade_lista_espera=1,
        rotulo_prioridade="baixa",
    ),
}

# Regra 2: prazo para o primeiro da fila confirmar a vaga liberada.
PRAZO_CONFIRMACAO_LISTA_ESPERA = timedelta(hours=48)
# Regra 3: reprovacoes que impedem nova matricula na disciplina.
MAX_REPROVACOES_POR_DISCIPLINA = 3
# Regra 5: minimo de matriculas confirmadas para a turma nao ser cancelada.
MIN_MATRICULAS_CONFIRMADAS_TURMA = 5
# Regra 7: trancamentos no semestre que levam o aluno a situacao "trancado".
MAX_TRANCAMENTOS_SEMESTRE = 3


def regras(categoria: CategoriaAluno) -> RegrasCategoria:
    return REGRAS_POR_CATEGORIA[CategoriaAluno(categoria)]
