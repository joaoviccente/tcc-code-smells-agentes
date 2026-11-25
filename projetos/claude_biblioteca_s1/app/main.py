from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.database import Base, engine
from app.erros import ErroNegocio
from app.routers import emprestimos, exemplares, livros, multas, relatorios, reservas, usuarios


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="API Biblioteca Universitaria", version="1.0.0", lifespan=lifespan)


@app.exception_handler(ErroNegocio)
async def _erro_negocio(_: Request, exc: ErroNegocio):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detalhe})


@app.exception_handler(IntegrityError)
async def _erro_integridade(_: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Violacao de integridade dos dados"})


for r in (usuarios, livros, exemplares, emprestimos, reservas, multas, relatorios):
    app.include_router(r.router)
