from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app import database
from app.erros import ErroNegocio
from app.routers import exemplares, livros, operacoes, usuarios


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
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.mensagem})


@app.exception_handler(IntegrityError)
async def _erro_integridade(_: Request, exc: IntegrityError):
    return JSONResponse(status_code=status.HTTP_409_CONFLICT,
                        content={"detail": "Violacao de integridade dos dados (registro duplicado ou vinculado)"})


app.include_router(usuarios.router)
app.include_router(livros.router)
app.include_router(exemplares.router)
app.include_router(operacoes.emprestimos)
app.include_router(operacoes.reservas)
app.include_router(operacoes.multas)
app.include_router(operacoes.relatorios_router)


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok"}
