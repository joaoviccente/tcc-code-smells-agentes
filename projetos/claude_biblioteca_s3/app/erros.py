from fastapi import status


class ErroNegocio(Exception):
    """Erro de regra de negocio, convertido em resposta HTTP pelo handler global."""

    def __init__(self, mensagem: str, status_code: int = status.HTTP_409_CONFLICT):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status_code = status_code


class NaoEncontrado(ErroNegocio):
    def __init__(self, recurso: str, id_: int):
        super().__init__(f"{recurso} {id_} nao encontrado", status.HTTP_404_NOT_FOUND)
