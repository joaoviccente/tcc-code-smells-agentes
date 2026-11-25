from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
from app.routers import (
    clientes_router,
    contas_router,
    cartoes_router,
    transacoes_router,
    faturas_router,
    tarifas_router,
    relatorios_router,
    rotinas_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa as tabelas do banco de dados relacional
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="API de Gestão de Contas Correntes",
    description="API REST em Python para gestão de contas correntes bancárias, cartões, faturas, tarifas e relatórios.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registro dos Roteadores
app.include_router(clientes_router)
app.include_router(contas_router)
app.include_router(cartoes_router)
app.include_router(transacoes_router)
app.include_router(faturas_router)
app.include_router(tarifas_router)
app.include_router(relatorios_router)
app.include_router(rotinas_router)


@app.get("/", tags=["Health Check"])
def root():
    return {
        "status": "online",
        "service": "API de Gestão de Contas Correntes",
        "docs_url": "/docs",
    }
