"""Parametros de negocio. Valores monetarios em centavos para evitar erro de ponto flutuante."""
from dataclasses import dataclass
from datetime import timedelta

from app.models import Categoria


@dataclass(frozen=True)
class RegraCategoria:
    limite_exemplares: int
    prazo_dias: int
    max_renovacoes: int
    multa_diaria_centavos: int
    teto_multa_centavos: int


REGRAS: dict[Categoria, RegraCategoria] = {
    Categoria.ALUNO: RegraCategoria(limite_exemplares=3, prazo_dias=7, max_renovacoes=2,
                                    multa_diaria_centavos=100, teto_multa_centavos=3000),
    Categoria.PROFESSOR: RegraCategoria(limite_exemplares=8, prazo_dias=30, max_renovacoes=4,
                                        multa_diaria_centavos=50, teto_multa_centavos=5000),
    Categoria.VISITANTE: RegraCategoria(limite_exemplares=1, prazo_dias=3, max_renovacoes=0,
                                        multa_diaria_centavos=200, teto_multa_centavos=2000),
}

ATRASO_PARA_SUSPENSAO_DIAS = 15          # suspende se atraso > 15 dias
FATOR_DURACAO_SUSPENSAO = 2              # suspensao = 2 x dias de atraso
PRAZO_RETIRADA_RESERVA = timedelta(hours=48)
TOLERANCIA_PERDAO_PROFESSOR_DIAS = 2     # multa de professor perdoada se atraso <= 2 dias
ATRASO_PARA_BAIXA_DIAS = 60              # devolucao com atraso > 60 dias baixa o exemplar
