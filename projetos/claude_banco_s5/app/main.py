from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.database import Base, engine
from app.erros import ErroDominio
from app.routers import cadastros, operacoes


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="API Bancaria - Contas Correntes",
    version="1.0.0",
    description="Gestao de clientes, contas, transacoes, cartoes, faturas e tarifas.",
    lifespan=lifespan,
)


@app.exception_handler(ErroDominio)
async def erro_dominio(_req: Request, exc: ErroDominio):
    return JSONResponse(status_code=exc.status_code,
                        content={"erro": exc.codigo, "detail": exc.mensagem})


@app.exception_handler(RequestValidationError)
async def erro_validacao(_req: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={
        "erro": "dados_invalidos", "detail": jsonable_encoder(exc.errors())})


@app.exception_handler(IntegrityError)
async def erro_integridade(_req: Request, _exc: IntegrityError):
    return JSONResponse(status_code=409, content={
        "erro": "conflito", "detail": "Violacao de integridade dos dados"})


for r in (cadastros.clientes, cadastros.contas, cadastros.cartoes, operacoes.transacoes,
          operacoes.extratos, operacoes.faturas, operacoes.tarifas, operacoes.relatorios,
          operacoes.processamentos):
    app.include_router(r)
