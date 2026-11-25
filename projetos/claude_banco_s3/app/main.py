from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app import models  # noqa: F401  (registra os modelos)
from app.database import Base, engine
from app.errors import ErroNegocio
from app.routers import cadastros, operacoes


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="API Banco - Contas Correntes", version="1.0.0", lifespan=lifespan)


@app.exception_handler(ErroNegocio)
async def _erro_negocio(_req: Request, exc: ErroNegocio):
    return JSONResponse(status_code=exc.status_code, content={"erro": exc.codigo, "mensagem": exc.mensagem})


@app.exception_handler(IntegrityError)
async def _erro_integridade(_req: Request, _exc: IntegrityError):
    return JSONResponse(status_code=409, content={"erro": "violacao_integridade",
                                                  "mensagem": "Operacao viola restricao de integridade."})


for r in (cadastros.clientes, cadastros.contas, cadastros.cartoes, operacoes.transacoes, operacoes.faturas,
          operacoes.tarifas, operacoes.relatorios, operacoes.rotinas_r):
    app.include_router(r)


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}
