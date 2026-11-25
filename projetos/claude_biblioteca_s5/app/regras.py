"""Parametros de negocio por categoria de usuario (valores exatos do enunciado)."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RegraCategoria:
    limite_exemplares: int
    prazo_dias: int
    max_renovacoes: int
    multa_por_dia: Decimal
    teto_multa: Decimal


REGRAS: dict[str, RegraCategoria] = {
    "aluno": RegraCategoria(
        limite_exemplares=3, prazo_dias=7, max_renovacoes=2,
        multa_por_dia=Decimal("1.00"), teto_multa=Decimal("30.00"),
    ),
    "professor": RegraCategoria(
        limite_exemplares=8, prazo_dias=30, max_renovacoes=4,
        multa_por_dia=Decimal("0.50"), teto_multa=Decimal("50.00"),
    ),
    "visitante": RegraCategoria(
        limite_exemplares=1, prazo_dias=3, max_renovacoes=0,
        multa_por_dia=Decimal("2.00"), teto_multa=Decimal("20.00"),
    ),
}

# Regra 2: atraso estritamente superior a 15 dias suspende; suspensao = 2x dias de atraso.
LIMITE_ATRASO_SUSPENSAO_DIAS = 15
FATOR_SUSPENSAO = 2

# Regra 4: prazo para retirar uma reserva disponivel.
PRAZO_RETIRADA_RESERVA_HORAS = 48

# Regra 5: perdao automatico de multa de professor com atraso de ate 2 dias.
PERDAO_PROFESSOR_MAX_DIAS = 2

# Regra 7: atraso estritamente superior a 60 dias na devolucao baixa o exemplar.
LIMITE_ATRASO_BAIXA_DIAS = 60


def regra(categoria: str) -> RegraCategoria:
    return REGRAS[categoria]
