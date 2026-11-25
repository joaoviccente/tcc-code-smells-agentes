from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
import app.models  # Garante o registro de todos os modelos no SQLAlchemy Base
from app.routers import (
    clientes_router,
    contas_router,
    cartoes_router,
    transacoes_router,
    faturas_router,
    tarifas_router,
    relatorios_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cria todas as tabelas no banco de dados se não existirem
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="API de Gestão de Contas Correntes",
    description=(
        "API REST em Python para gestão bancária completa, contemplando clientes, contas, "
        "cartões, faturas, tarifas e transações financeiras com regras de negócio por categoria."
    ),
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

# Registro dos roteadores
app.include_router(clientes_router)
app.include_router(contas_router)
app.include_router(cartoes_router)
app.include_router(transacoes_router)
app.include_router(faturas_router)
app.include_router(tarifas_router)
app.include_router(relatorios_router)


@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "online",
        "sistema": "API Gestão de Contas Correntes",
        "versao": "1.0.0"
    }
