"""Parametros de negocio da biblioteca.

Todos os valores monetarios sao armazenados em CENTAVOS (inteiros) para evitar
erros de arredondamento de ponto flutuante.
"""
from dataclasses import dataclass

from .enums import Categoria


@dataclass(frozen=True)
class RegraCategoria:
    limite_exemplares: int
    prazo_dias: int
    max_renovacoes: int
    multa_diaria_centavos: int
    teto_multa_centavos: int


REGRAS_POR_CATEGORIA: dict[Categoria, RegraCategoria] = {
    # Aluno: 3 exemplares; 7 dias; 2 renovacoes; R$ 1,00/dia; teto R$ 30,00
    Categoria.aluno: RegraCategoria(3, 7, 2, 100, 3000),
    # Professor: 8 exemplares; 30 dias; 4 renovacoes; R$ 0,50/dia; teto R$ 50,00
    Categoria.professor: RegraCategoria(8, 30, 4, 50, 5000),
    # Visitante: 1 exemplar; 3 dias; 0 renovacoes; R$ 2,00/dia; teto R$ 20,00
    Categoria.visitante: RegraCategoria(1, 3, 0, 200, 2000),
}

# Regra 2: atraso superior a 15 dias suspende; suspensao = 2 x dias de atraso
DIAS_ATRASO_PARA_SUSPENSAO = 15
FATOR_DIAS_SUSPENSAO = 2

# Regra 4: prazo para retirada de reserva disponivel
HORAS_PARA_RETIRADA_RESERVA = 48

# Regra 5: multa de professor perdoada se atraso de ate 2 dias
DIAS_PERDAO_PROFESSOR = 2

# Regra 7: devolucao com mais de 60 dias de atraso -> exemplar baixado + multa no teto
DIAS_ATRASO_PARA_BAIXA = 60


def regra(categoria: Categoria | str) -> RegraCategoria:
    return REGRAS_POR_CATEGORIA[Categoria(categoria)]
