from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from typing import Dict
from app.models import CategoriaUsuario

@dataclass(frozen=True)
class RegraCategoria:
    limite_exemplares: int
    prazo_dias: int
    max_renovacoes: int
    valor_multa_dia: Decimal
    teto_multa: Decimal

REGRAS_POR_CATEGORIA: Dict[CategoriaUsuario, RegraCategoria] = {
    CategoriaUsuario.aluno: RegraCategoria(
        limite_exemplares=3,
        prazo_dias=7,
        max_renovacoes=2,
        valor_multa_dia=Decimal("1.00"),
        teto_multa=Decimal("30.00"),
    ),
    CategoriaUsuario.professor: RegraCategoria(
        limite_exemplares=8,
        prazo_dias=30,
        max_renovacoes=4,
        valor_multa_dia=Decimal("0.50"),
        teto_multa=Decimal("50.00"),
    ),
    CategoriaUsuario.visitante: RegraCategoria(
        limite_exemplares=1,
        prazo_dias=3,
        max_renovacoes=0,
        valor_multa_dia=Decimal("2.00"),
        teto_multa=Decimal("20.00"),
    ),
}

DIAS_ATRASO_SUSPENSAO = 15
FATOR_SUSPENSAO = 2
HORAS_LIMITE_RETIRADA_RESERVA = 48
DIAS_TOLERANCIA_PROFESSOR = 2
DIAS_ATRASO_BAIXA = 60

def get_regras_categoria(categoria: CategoriaUsuario) -> RegraCategoria:
    if isinstance(categoria, str):
        categoria = CategoriaUsuario(categoria)
    return REGRAS_POR_CATEGORIA[categoria]

def calcular_dias_atraso(data_prevista: datetime, data_devolucao: datetime) -> int:
    """Calcula dias corridos de atraso entre a data prevista e a data de devolução."""
    if data_devolucao <= data_prevista:
        return 0
    # Diferença em dias de calendário
    diff_dias = (data_devolucao.date() - data_prevista.date()).days
    if diff_dias > 0:
        return diff_dias
    # Se na mesma data de calendário, mas horário posterior:
    if data_devolucao > data_prevista:
        return 1
    return 0
