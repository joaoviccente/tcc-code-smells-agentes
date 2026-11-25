from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import Base, engine
from .errors import ErroAPI, tratar_erro_api
from .routers import alunos, disciplinas, matriculas, relatorios, turmas


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="API de Gestão de Matrículas Acadêmicas",
    version="1.0.0",
    description=(
        "Gestão de alunos, disciplinas, turmas, matrículas, lista de espera, histórico "
        "e relatórios. Datas em UTC."
    ),
    lifespan=lifespan,
)
app.add_exception_handler(ErroAPI, tratar_erro_api)

for r in (alunos, disciplinas, turmas, matriculas, relatorios):
    app.include_router(r.router)


@app.get("/health", tags=["Infra"])
def health():
    return {"status": "ok"}
