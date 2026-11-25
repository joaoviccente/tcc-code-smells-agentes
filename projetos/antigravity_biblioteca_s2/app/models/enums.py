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


class EstadoMulta(str, Enum):
    ABERTA = "aberta"
    PAGA = "paga"
    PERDOADA = "perdoada"
