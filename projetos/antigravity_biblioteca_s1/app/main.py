from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.database import Base, engine
from app.routers import (
    usuarios,
    livros,
    exemplares,
    emprestimos,
    reservas,
    multas,
    relatorios,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa as tabelas no banco de dados relacional
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API REST para Gestão de Biblioteca Universitária com controle de usuários, livros, exemplares, empréstimos, reservas, multas e relatórios.",
    lifespan=lifespan,
)

# Inclusão dos roteadores
app.include_router(usuarios.router)
app.include_router(livros.router)
app.include_router(exemplares.router)
app.include_router(emprestimos.router)
app.include_router(reservas.router)
app.include_router(multas.router)
app.include_router(relatorios.router)

@app.get("/", tags=["Health Check"])
def root():
    return {
        "status": "online",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }
