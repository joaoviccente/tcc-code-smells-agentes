from fastapi import Request
from fastapi.responses import JSONResponse


class ErroNegocio(Exception):
    """Erro de dominio com codigo HTTP e codigo simbolico estavel."""

    def __init__(self, status: int, codigo: str, mensagem: str, detalhes=None):
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhes = detalhes


class NaoEncontrado(ErroNegocio):
    def __init__(self, entidade: str, id_):
        super().__init__(404, f"{entidade.upper()}_NAO_ENCONTRADO",
                         f"{entidade} {id_} nao encontrado(a)")


class Conflito(ErroNegocio):
    def __init__(self, codigo: str, mensagem: str, detalhes=None):
        super().__init__(409, codigo, mensagem, detalhes)


class RegraViolada(ErroNegocio):
    def __init__(self, codigo: str, mensagem: str, detalhes=None):
        super().__init__(422, codigo, mensagem, detalhes)


async def tratar_erro_negocio(_: Request, exc: ErroNegocio):
    corpo = {"erro": exc.codigo, "mensagem": exc.mensagem}
    if exc.detalhes is not None:
        corpo["detalhes"] = exc.detalhes
    return JSONResponse(status_code=exc.status, content=corpo)
