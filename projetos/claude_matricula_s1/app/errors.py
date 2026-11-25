from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


class ErroNegocio(Exception):
    def __init__(self, status_code: int, codigo: str, mensagem: str, detalhes=None):
        self.status_code = status_code
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhes = detalhes


def nao_encontrado(entidade: str, id_) -> ErroNegocio:
    return ErroNegocio(404, f"{entidade}_nao_encontrado", f"{entidade.capitalize()} {id_} nao encontrado(a)")


async def handler_erro_negocio(_: Request, exc: ErroNegocio):
    corpo = {"erro": exc.codigo, "mensagem": exc.mensagem}
    if exc.detalhes is not None:
        corpo["detalhes"] = exc.detalhes
    return JSONResponse(status_code=exc.status_code, content=corpo)


async def handler_integridade(_: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=409,
        content={"erro": "violacao_integridade", "mensagem": "Operacao viola restricao de integridade do banco"},
    )
