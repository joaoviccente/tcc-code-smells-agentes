import unicodedata

from fastapi import Request
from fastapi.responses import JSONResponse


class ErroAPI(Exception):
    """Erro de domínio convertido em resposta HTTP padronizada."""

    def __init__(self, status_code: int, codigo: str, mensagem: str, detalhes=None):
        super().__init__(mensagem)
        self.status_code = status_code
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhes = detalhes


def nao_encontrado(entidade: str, ident) -> ErroAPI:
    sem_acento = unicodedata.normalize("NFKD", entidade).encode("ascii", "ignore").decode()
    codigo = sem_acento.upper().replace("-", "_").replace(" ", "_") + "_NAO_ENCONTRADO"
    return ErroAPI(404, codigo, f"{entidade} {ident} não encontrado(a).")


def regra(codigo: str, mensagem: str, detalhes=None) -> ErroAPI:
    """Violação de regra de negócio (requisição válida, mas não processável)."""
    return ErroAPI(422, codigo, mensagem, detalhes)


def conflito(codigo: str, mensagem: str, detalhes=None) -> ErroAPI:
    """Conflito com o estado atual do recurso."""
    return ErroAPI(409, codigo, mensagem, detalhes)


async def tratar_erro_api(_request: Request, exc: ErroAPI) -> JSONResponse:
    corpo = {"erro": {"codigo": exc.codigo, "mensagem": exc.mensagem}}
    if exc.detalhes is not None:
        corpo["erro"]["detalhes"] = exc.detalhes
    return JSONResponse(status_code=exc.status_code, content=corpo)
