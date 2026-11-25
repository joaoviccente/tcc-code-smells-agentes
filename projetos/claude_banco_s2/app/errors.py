from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ErroAplicacao(Exception):
    status_code = 422

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NaoEncontrado(ErroAplicacao):
    status_code = 404


class Conflito(ErroAplicacao):
    """Operacao incompativel com o estado atual do recurso."""
    status_code = 409


class RegraViolada(ErroAplicacao):
    """Regra de negocio violada (limite, saldo, prazo...)."""
    status_code = 422


def registrar_handlers(app: FastAPI) -> None:
    @app.exception_handler(ErroAplicacao)
    async def _handler(_: Request, exc: ErroAplicacao):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
