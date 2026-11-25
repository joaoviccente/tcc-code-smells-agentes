from dataclasses import dataclass
from typing import Dict
from app.models.enums import CategoriaUsuario


@dataclass(frozen=True)
class RegrasCategoria:
    limite_exemplares: int
    prazo_dias: int
    max_renovacoes: int
    multa_diaria: float
    teto_multa: float


# REGRAS POR CATEGORIA DE USUÁRIO:
# Aluno: limite de 3 exemplares; prazo de 7 dias; 2 renovações; multa de R$ 1,00 por dia; teto de R$ 30,00.
# Professor: limite de 8 exemplares; prazo de 30 dias; 4 renovações; multa de R$ 0,50 por dia; teto de R$ 50,00.
# Visitante: limite de 1 exemplar; prazo de 3 dias; nenhuma renovação; multa de R$ 2,00 por dia; teto de R$ 20,00.
REGRAS_CATEGORIA: Dict[CategoriaUsuario, RegrasCategoria] = {
    CategoriaUsuario.ALUNO: RegrasCategoria(
        limite_exemplares=3,
        prazo_dias=7,
        max_renovacoes=2,
        multa_diaria=1.00,
        teto_multa=30.00,
    ),
    CategoriaUsuario.PROFESSOR: RegrasCategoria(
        limite_exemplares=8,
        prazo_dias=30,
        max_renovacoes=4,
        multa_diaria=0.50,
        teto_multa=50.00,
    ),
    CategoriaUsuario.VISITANTE: RegrasCategoria(
        limite_exemplares=1,
        prazo_dias=3,
        max_renovacoes=0,
        multa_diaria=2.00,
        teto_multa=20.00,
    ),
}

# Parâmetros gerais das regras de negócio
HORAS_LIMITE_RETIRADA_RESERVA = 48  # Regra 4: 48 horas para retirar reserva disponível
DIAS_LIMITE_SUSPENSAO = 15          # Regra 2: atraso superior a 15 dias suspende usuário
MULTIPLICADOR_SUSPENSAO = 2        # Regra 2: suspensão dura o dobro dos dias de atraso
DIAS_LIMITE_BAIXA_ATRASO = 60      # Regra 7: mais de 60 dias de atraso marca exemplar como baixado
DIAS_TOLERANCIA_PROFESSOR = 2      # Regra 5: professor perdoado se atraso de até 2 dias
