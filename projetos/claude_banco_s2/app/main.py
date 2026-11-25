import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import clock
from app.config import INTERVALO_ROTINAS_SEGUNDOS
from app.database import Base, SessionLocal, engine
from app.errors import registrar_handlers
from app.routers import cartoes, clientes, contas, relatorios, transacoes
from app.services import rotinas

log = logging.getLogger("banco")


def executar_rotinas() -> None:
    with SessionLocal() as db:
        agora = clock.agora()
        rotinas.processamento_diario(db, agora)
        rotinas.tarifas_mensais(db, None, agora)


async def _agendador(intervalo: int) -> None:
    while True:
        try:
            await asyncio.to_thread(executar_rotinas)
        except Exception:  # noqa: BLE001 - o agendador nao pode morrer
            log.exception("Falha ao executar rotinas periodicas")
        await asyncio.sleep(intervalo)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    tarefa = None
    if INTERVALO_ROTINAS_SEGUNDOS > 0:
        tarefa = asyncio.create_task(_agendador(INTERVALO_ROTINAS_SEGUNDOS))
    yield
    if tarefa:
        tarefa.cancel()


app = FastAPI(
    title="API Banco - Contas Correntes",
    version="1.0.0",
    description="Gestao de clientes, contas, transacoes, cartoes, faturas e tarifas.",
    lifespan=lifespan,
)
registrar_handlers(app)

app.include_router(clientes.router)
app.include_router(contas.router)
app.include_router(transacoes.router)
app.include_router(cartoes.router)
app.include_router(cartoes.router_faturas)
app.include_router(relatorios.router)
app.include_router(relatorios.router_rotinas)
