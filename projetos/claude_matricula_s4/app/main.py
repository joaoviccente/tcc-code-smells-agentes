from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (registra as tabelas)
from app.database import Base, engine
from app.errors import ErroNegocio, tratar_erro_negocio
from app.routers import alunos, disciplinas, matriculas, outros, turmas


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="API de Matriculas Academicas", version="1.0.0", lifespan=lifespan)
app.add_exception_handler(ErroNegocio, tratar_erro_negocio)


@app.exception_handler(IntegrityError)
async def _integridade(_, exc: IntegrityError):
    return JSONResponse(status_code=409, content={
        "erro": "VIOLACAO_INTEGRIDADE", "mensagem": "Operacao viola restricao do banco"})


for r in (alunos.router, disciplinas.router, turmas.router, matriculas.router,
          outros.historico, outros.periodos, outros.relatorios):
    app.include_router(r)
