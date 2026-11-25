"""Excecoes de dominio, mapeadas para codigos HTTP em app.main."""


class ErroDominio(Exception):
    status_code = 400
    codigo = "erro"

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class NaoEncontrado(ErroDominio):
    """Recurso inexistente -> 404."""
    status_code = 404
    codigo = "nao_encontrado"


class Conflito(ErroDominio):
    """Estado atual do recurso impede a operacao (conta/cliente bloqueado,
    duplicidade, transicao de estado invalida) -> 409."""
    status_code = 409
    codigo = "conflito"


class RegraNegocio(ErroDominio):
    """Operacao viola regra de negocio (saldo, limites, prazos) -> 422."""
    status_code = 422
    codigo = "regra_de_negocio"
