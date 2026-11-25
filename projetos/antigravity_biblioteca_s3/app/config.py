from dataclasses import dataclass
from decimal import Decimal
from typing import Dict


@dataclass(frozen=True)
class RegraCategoria:
    limite_exemplares: int
    prazo_dias: int
    max_renovacoes: int
    multa_diaria: Decimal
    teto_multa: Decimal


REGRAS_CATEGORIA: Dict[str, RegraCategoria] = {
    "aluno": RegraCategoria(
        limite_exemplares=3,
        prazo_dias=7,
        max_renovacoes=2,
        multa_diaria=Decimal("1.00"),
        teto_multa=Decimal("30.00"),
    ),
    "professor": RegraCategoria(
        limite_exemplares=8,
        prazo_dias=30,
        max_renovacoes=4,
        multa_diaria=Decimal("0.50"),
        teto_multa=Decimal("50.00"),
    ),
    "visitante": RegraCategoria(
        limite_exemplares=1,
        prazo_dias=3,
        max_renovacoes=0,
        multa_diaria=Decimal("2.00"),
        teto_multa=Decimal("20.00"),
    ),
}

# Constantes de regras de negócio
HORAS_LIMITE_RETIRADA_RESERVA: int = 48
DIAS_LIMITE_SUSPENSAO_AUTOMATICA: int = 15
FATOR_DURACAO_SUSPENSAO: int = 2
DIAS_LIMITE_BAIXA_POR_ATRASO: int = 60
DIAS_TOLERANCIA_PROFESSOR_PERDAO: int = 2
