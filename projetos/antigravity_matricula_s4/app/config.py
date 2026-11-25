from dataclasses import dataclass
from enum import Enum
from typing import Dict


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
    REPROVADO_POR_FALTA = "reprovado_por_falta"
    TRANCADO = "trancado"


@dataclass(frozen=True)
class RegrasCategoria:
    max_creditos_semestre: int
    max_trancamentos_disciplina: int
    prazo_cancelamento_dias: int
    prioridade_lista_espera: int  # 1 = Alta, 2 = Média, 3 = Baixa (menor número = maior prioridade)


# Regras exatas definidas na especificação:
# Graduação: máx 28 créditos, até 2 trancamentos por disciplina, prazo cancelamento 15 dias, prioridade média
# Pós: máx 16 créditos, 1 trancamento por disciplina, prazo cancelamento 30 dias, prioridade alta
# Especial: máx 8 créditos, nenhum trancamento (0), prazo cancelamento 7 dias, prioridade baixa
REGRAS_CATEGORIAS: Dict[CategoriaAluno, RegrasCategoria] = {
    CategoriaAluno.POS: RegrasCategoria(
        max_creditos_semestre=16,
        max_trancamentos_disciplina=1,
        prazo_cancelamento_dias=30,
        prioridade_lista_espera=1,  # Alta
    ),
    CategoriaAluno.GRADUACAO: RegrasCategoria(
        max_creditos_semestre=28,
        max_trancamentos_disciplina=2,
        prazo_cancelamento_dias=15,
        prioridade_lista_espera=2,  # Média
    ),
    CategoriaAluno.ESPECIAL: RegrasCategoria(
        max_creditos_semestre=8,
        max_trancamentos_disciplina=0,
        prazo_cancelamento_dias=7,
        prioridade_lista_espera=3,  # Baixa
    ),
}

# Constantes de regras de negócio
MAX_REPROVACOES_DISCIPLINA = 3
HORAS_EXPIRACAO_VAGA_FILA = 48
MINIMO_MATRICULAS_TURMA = 5
MAX_TRANCAMENTOS_SEMESTRE_ALUNO = 3

DATABASE_URL = "sqlite:///./matriculas.db"
