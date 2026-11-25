from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.database import Base, engine
from app.errors import ErroNegocio
from app.routers.cadastros import cartoes, clientes, contas
from app.routers.operacoes import faturas_router, relatorios_router, rotinas_router, transacoes_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="API de Contas Correntes",
    description="Gestao de clientes, contas, transacoes, cartoes, faturas e tarifas.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(ErroNegocio)
async def erro_negocio(_: Request, exc: ErroNegocio):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.mensagem})


@app.exception_handler(IntegrityError)
async def erro_integridade(_: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Violacao de integridade dos dados"})


for router in (clientes, contas, cartoes, transacoes_router, faturas_router, rotinas_router, relatorios_router):
    app.include_router(router)
