from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from . import database
from .erros import ErroNegocio
from .routers import exemplares, livros, operacoes, relatorios, usuarios


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.Base.metadata.create_all(bind=database.engine)
    yield


app = FastAPI(
    title="API Biblioteca Universitaria",
    version="1.0.0",
    description="Gestao de usuarios, acervo, emprestimos, reservas e multas.",
    lifespan=lifespan,
)


@app.exception_handler(ErroNegocio)
async def _erro_negocio(_: Request, exc: ErroNegocio):
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc.mensagem, "codigo": exc.codigo})


@app.exception_handler(IntegrityError)
async def _erro_integridade(_: Request, exc: IntegrityError):
    return JSONResponse(status_code=409,
                        content={"detail": "Violacao de integridade dos dados", "codigo": "integridade"})


for r in (usuarios.router, livros.router, exemplares.router, operacoes.emprestimos,
          operacoes.reservas, operacoes.multas, relatorios.router):
    app.include_router(r)
