from decimal import Decimal
from app.models.enums import CategoriaUsuario

REGRAS_CATEGORIA = {
    CategoriaUsuario.ALUNO: {
        "limite_exemplares": 3,
        "prazo_dias": 7,
        "limite_renovacoes": 2,
        "multa_diaria": Decimal("1.00"),
        "teto_multa": Decimal("30.00"),
    },
    CategoriaUsuario.PROFESSOR: {
        "limite_exemplares": 8,
        "prazo_dias": 30,
        "limite_renovacoes": 4,
        "multa_diaria": Decimal("0.50"),
        "teto_multa": Decimal("50.00"),
    },
    CategoriaUsuario.VISITANTE: {
        "limite_exemplares": 1,
        "prazo_dias": 3,
        "limite_renovacoes": 0,
        "multa_diaria": Decimal("2.00"),
        "teto_multa": Decimal("20.00"),
    },
}

DIAS_ATRASO_SUSPENSAO = 15
FATOR_SUSPENSAO = 2
HORAS_EXPIRACAO_RESERVA = 48
DIAS_LIMITE_BAIXA = 60
DIAS_PERDAO_PROFESSOR = 2
