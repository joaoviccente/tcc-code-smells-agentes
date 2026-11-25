from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class CategoriaUsuario(str, Enum):
    ALUNO = "aluno"
    PROFESSOR = "professor"
    VISITANTE = "visitante"


class SituacaoUsuario(str, Enum):
    ATIVO = "ativo"
    SUSPENSO = "suspenso"


class EstadoExemplar(str, Enum):
    DISPONIVEL = "disponivel"
    EMPRESTADO = "emprestado"
    RESERVADO = "reservado"
    EM_REPARO = "em_reparo"
    BAIXADO = "baixado"


class EstadoEmprestimo(str, Enum):
    ATIVO = "ativo"
    DEVOLVIDO = "devolvido"
    ATRASADO = "atrasado"


class EstadoReserva(str, Enum):
    AGUARDANDO = "aguardando"
    DISPONIVEL = "disponivel"
    EXPIRADA = "expirada"
    CANCELADA = "cancelada"
    CONCLUIDA = "concluida"


class EstadoMulta(str, Enum):
    ABERTA = "aberta"
    PAGA = "paga"
    PERDOADA = "perdoada"


@dataclass(frozen=True)
class RegrasCategoria:
    limite_exemplares: int
    prazo_dias: int
    limite_renovacoes: int
    multa_por_dia: Decimal
    teto_multa: Decimal


REGRAS_POR_CATEGORIA: dict[CategoriaUsuario, RegrasCategoria] = {
    CategoriaUsuario.ALUNO: RegrasCategoria(
        limite_exemplares=3,
        prazo_dias=7,
        limite_renovacoes=2,
        multa_por_dia=Decimal("1.00"),
        teto_multa=Decimal("30.00"),
    ),
    CategoriaUsuario.PROFESSOR: RegrasCategoria(
        limite_exemplares=8,
        prazo_dias=30,
        limite_renovacoes=4,
        multa_por_dia=Decimal("0.50"),
        teto_multa=Decimal("50.00"),
    ),
    CategoriaUsuario.VISITANTE: RegrasCategoria(
        limite_exemplares=1,
        prazo_dias=3,
        limite_renovacoes=0,
        multa_por_dia=Decimal("2.00"),
        teto_multa=Decimal("20.00"),
    ),
}

DATABASE_URL = "sqlite:///./biblioteca.db"
PRAZO_RETIRADA_RESERVA_HORAS = 48
DIAS_LIMITE_SUSPENSAO = 15
DIAS_LIMITE_BAIXA = 60
DIAS_PERDAO_PROFESSOR = 2
