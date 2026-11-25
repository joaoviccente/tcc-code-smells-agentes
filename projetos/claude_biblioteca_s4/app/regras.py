"""Parametros de negocio por categoria de usuario (valores exatos do enunciado)."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RegraCategoria:
    limite_exemplares: int
    prazo_dias: int
    max_renovacoes: int
    multa_diaria: Decimal
    teto_multa: Decimal


REGRAS: dict[str, RegraCategoria] = {
    "aluno": RegraCategoria(3, 7, 2, Decimal("1.00"), Decimal("30.00")),
    "professor": RegraCategoria(8, 30, 4, Decimal("0.50"), Decimal("50.00")),
    "visitante": RegraCategoria(1, 3, 0, Decimal("2.00"), Decimal("20.00")),
}

# Regra 2: atraso superior a este numero de dias suspende o usuario.
DIAS_ATRASO_SUSPENSAO = 15
# Regra 2: a suspensao dura este multiplo dos dias de atraso.
FATOR_SUSPENSAO = 2
# Regra 4: prazo para retirar uma reserva que ficou disponivel.
HORAS_RETIRADA_RESERVA = 48
# Regra 5: multa de professor perdoada se o atraso for de ate N dias.
DIAS_PERDAO_PROFESSOR = 2
# Regra 7: devolucao com atraso superior a N dias baixa o exemplar.
DIAS_ATRASO_BAIXA = 60


def regra(categoria: str) -> RegraCategoria:
    return REGRAS[categoria]
