from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import database
from .routers import circulacao, exemplares, livros, relatorios, usuarios


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.Base.metadata.create_all(bind=database.engine)
    yield


app = FastAPI(
    title="API Biblioteca Universitaria",
    version="1.0.0",
    description="Gestao de usuarios, acervo, emprestimos, reservas e multas.",
    lifespan=lifespan,
)

app.include_router(usuarios.router)
app.include_router(livros.router)
app.include_router(exemplares.router)
app.include_router(circulacao.emprestimos)
app.include_router(circulacao.reservas)
app.include_router(circulacao.multas)
app.include_router(relatorios.router)
