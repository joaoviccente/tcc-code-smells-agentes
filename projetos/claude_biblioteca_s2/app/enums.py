from enum import StrEnum


class Categoria(StrEnum):
    aluno = "aluno"
    professor = "professor"
    visitante = "visitante"


class SituacaoUsuario(StrEnum):
    ativo = "ativo"
    suspenso = "suspenso"


class EstadoExemplar(StrEnum):
    disponivel = "disponivel"
    emprestado = "emprestado"
    reservado = "reservado"
    em_reparo = "em_reparo"
    baixado = "baixado"


class EstadoEmprestimo(StrEnum):
    ativo = "ativo"
    devolvido = "devolvido"
    atrasado = "atrasado"


class EstadoReserva(StrEnum):
    aguardando = "aguardando"
    disponivel = "disponivel"
    expirada = "expirada"
    cancelada = "cancelada"
    # Estado adicional: reserva concluida pela retirada do exemplar.
    atendida = "atendida"


class EstadoMulta(StrEnum):
    aberta = "aberta"
    paga = "paga"
    perdoada = "perdoada"


ESTADOS_EMPRESTIMO_EM_ABERTO = (EstadoEmprestimo.ativo, EstadoEmprestimo.atrasado)
ESTADOS_RESERVA_NA_FILA = (EstadoReserva.aguardando, EstadoReserva.disponivel)
ESTADOS_EXEMPLAR_EM_CIRCULACAO = (
    EstadoExemplar.disponivel,
    EstadoExemplar.emprestado,
    EstadoExemplar.reservado,
)
