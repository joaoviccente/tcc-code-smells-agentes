import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from . import clock
from .database import Base, SessionLocal, engine
from .errors import ErroNegocio
from .routers import cartoes, clientes, contas, faturas, relatorios, transacoes
from .services import rotinas

log = logging.getLogger("banco")
INTERVALO_ROTINA_SEG = int(os.getenv("BANCO_INTERVALO_ROTINA_SEG", "3600"))
ROTINA_AUTOMATICA = os.getenv("BANCO_ROTINA_AUTOMATICA", "1") == "1"


def _executar_rotina() -> None:
    with SessionLocal() as db:
        rotinas.processar(db, clock.agora().date())


async def _agendador():
    while True:
        try:
            await asyncio.to_thread(_executar_rotina)
        except Exception:  # pragma: no cover - apenas registro
            log.exception("Falha no processamento diario")
        await asyncio.sleep(INTERVALO_ROTINA_SEG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    tarefa = asyncio.create_task(_agendador()) if ROTINA_AUTOMATICA else None
    yield
    if tarefa:
        tarefa.cancel()


app = FastAPI(
    title="API Banco - Contas Correntes",
    version="1.0.0",
    description="Gestao de clientes, contas, transacoes, cartoes, faturas e tarifas.",
    lifespan=lifespan,
)


@app.exception_handler(ErroNegocio)
async def _erro_negocio(request: Request, exc: ErroNegocio):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.mensagem})


@app.exception_handler(IntegrityError)
async def _erro_integridade(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Violacao de integridade dos dados"})


for r in (clientes.router, contas.router, cartoes.router, transacoes.router, faturas.router, relatorios.router):
    app.include_router(r)
