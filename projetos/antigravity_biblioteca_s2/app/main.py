from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.database import Base, engine
from app.routers import (
    emprestimos_router,
    exemplares_router,
    livros_router,
    multas_router,
    relatorios_router,
    reservas_router,
    usuarios_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Criação das tabelas no banco de dados na inicialização
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="API de Gestão de Biblioteca Universitária",
    description="""
API REST completa para gestão de uma biblioteca universitária, implementando regras de negócio
para empréstimos, devoluções, renovações, reservas com fila de espera, cálculo de multas por categoria de usuário,
suspensões automáticas por atraso e relatórios analíticos.
    """,
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


@app.get("/", tags=["Status"])
def root():
    return {
        "status": "online",
        "mensagem": "API de Gestão de Biblioteca Universitária está em execução.",
        "documentacao": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health", tags=["Status"])
def health_check():
    return {"status": "healthy"}


# Inclusão dos roteadores
app.include_router(usuarios_router)
app.include_router(livros_router)
app.include_router(exemplares_router)
app.include_router(emprestimos_router)
app.include_router(reservas_router)
app.include_router(multas_router)
app.include_router(relatorios_router)
