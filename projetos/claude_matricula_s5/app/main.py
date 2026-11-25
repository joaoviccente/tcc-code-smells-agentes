from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from . import database
from .errors import ErroAPI
from .routers import alunos, disciplinas, historico, matriculas, relatorios, turmas
from .servicos import processar_expiracoes


@asynccontextmanager
async def lifespan(_app: FastAPI):
    database.criar_tabelas()
    yield


app = FastAPI(
    title="API de Matriculas Academicas",
    version="1.0.0",
    description="Gestao de alunos, disciplinas, turmas, matriculas, lista de espera e historico.",
    lifespan=lifespan,
)


@app.exception_handler(ErroAPI)
async def _erro_api(_request: Request, exc: ErroAPI):
    corpo = {"erro": exc.codigo, "mensagem": exc.mensagem}
    if exc.detalhes is not None:
        corpo["detalhes"] = exc.detalhes
    return JSONResponse(status_code=exc.status_code, content=corpo)


@app.exception_handler(IntegrityError)
async def _erro_integridade(_request: Request, _exc: IntegrityError):
    return JSONResponse(
        status_code=409,
        content={"erro": "VIOLACAO_INTEGRIDADE", "mensagem": "Operacao viola restricao de integridade."},
    )


for r in (alunos, disciplinas, turmas, matriculas, historico, relatorios):
    app.include_router(r.router)


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok"}


@app.post("/admin/processar-prazos", tags=["Sistema"], summary="Aplica expiracoes de 48h da lista de espera")
def processar_prazos():
    with database.SessionLocal() as db:
        return {"expiradas": processar_expiracoes(db)}
