class DomainError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NaoEncontrado(DomainError):
    status_code = 404


class Conflito(DomainError):
    """Conflito com o estado atual de um recurso (duplicidade, estado invalido, choque de horario)."""
    status_code = 409


class RegraNegocio(DomainError):
    """Requisicao bem formada, mas que viola uma regra de negocio."""
    status_code = 422
