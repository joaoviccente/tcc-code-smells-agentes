from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.database import Base, engine
from app.routers import (
    usuarios_router,
    livros_router,
    exemplares_router,
    emprestimos_router,
    reservas_router,
    multas_router,
    relatorios_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Criar tabelas no banco de dados na inicialização
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="API de Gestão de Biblioteca Universitária",
    description=(
        "API REST para gerenciamento de biblioteca universitária com controle de usuários, "
        "acervo, exemplares, empréstimos com regras por categoria, fila de reservas, "
        "multas por atraso e relatórios analíticos."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusão dos roteadores
app.include_router(usuarios_router)
app.include_router(livros_router)
app.include_router(exemplares_router)
app.include_router(emprestimos_router)
app.include_router(reservas_router)
app.include_router(multas_router)
app.include_router(relatorios_router)


@app.get("/", tags=["Status"])
def root():
    return {
        "status": "online",
        "api": "API de Gestão de Biblioteca Universitária",
        "docs": "/docs",
        "redoc": "/redoc",
    }
