from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError

from app.database import Base, engine
from app.errors import ErroNegocio, handler_erro_negocio, handler_integridade
from app.routers import alunos, disciplinas, matriculas, relatorios, turmas


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="API de Matriculas Academicas", version="1.0.0", lifespan=lifespan)
app.add_exception_handler(ErroNegocio, handler_erro_negocio)
app.add_exception_handler(IntegrityError, handler_integridade)

for r in (alunos, disciplinas, turmas, matriculas, relatorios):
    app.include_router(r.router)
