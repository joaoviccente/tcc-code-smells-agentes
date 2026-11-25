"""Configurações e regras do sistema de matrículas acadêmicas."""

from dataclasses import dataclass
from typing import Dict
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./matriculas.db")


@dataclass(frozen=True)
class RegrasCategoria:
    """Regras específicas por categoria de aluno."""
    max_creditos_semestre: int
    max_trancamentos_disciplina: int
    prazo_cancelamento_dias: int
    prioridade_espera: int  # 1: Alta (pos), 2: Média (graduacao), 3: Baixa (especial)
    nome_prioridade: str


REGRAS_POR_CATEGORIA: Dict[str, RegrasCategoria] = {
    "graduacao": RegrasCategoria(
        max_creditos_semestre=28,
        max_trancamentos_disciplina=2,
        prazo_cancelamento_dias=15,
        prioridade_espera=2,
        nome_prioridade="media",
    ),
    "pos": RegrasCategoria(
        max_creditos_semestre=16,
        max_trancamentos_disciplina=1,
        prazo_cancelamento_dias=30,
        prioridade_espera=1,
        nome_prioridade="alta",
    ),
    "especial": RegrasCategoria(
        max_creditos_semestre=8,
        max_trancamentos_disciplina=0,
        prazo_cancelamento_dias=7,
        prioridade_espera=3,
        nome_prioridade="baixa",
    ),
}

# Regras Globais de Negócio
MAX_REPROVACOES_IMPEDIMENTO: int = 3
HORAS_CONFIRMACAO_VAGA_LIBERADA: int = 48
MINIMO_MATRICULAS_TURMA: int = 5
MAX_TRANCAMENTOS_SEMESTRE_TRANCAR_ALUNO: int = 3
