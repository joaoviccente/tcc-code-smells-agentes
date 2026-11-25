from typing import Any


class ErroAPI(Exception):
    """Erro de dominio convertido em resposta HTTP pelo handler global."""

    def __init__(self, status_code: int, codigo: str, mensagem: str, detalhes: Any = None):
        super().__init__(mensagem)
        self.status_code = status_code
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhes = detalhes


class NaoEncontrado(ErroAPI):
    def __init__(self, mensagem: str):
        super().__init__(404, "NAO_ENCONTRADO", mensagem)


class Conflito(ErroAPI):
    def __init__(self, codigo: str, mensagem: str, detalhes: Any = None):
        super().__init__(409, codigo, mensagem, detalhes)


class RegraViolada(ErroAPI):
    def __init__(self, codigo: str, mensagem: str, detalhes: Any = None):
        super().__init__(422, codigo, mensagem, detalhes)
