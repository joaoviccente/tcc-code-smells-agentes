from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
import app.models  # Garante registro de todos os modelos
from app.routers import (
    alunos_router,
    disciplinas_router,
    turmas_router,
    matriculas_router,
    historico_router,
    relatorios_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa as tabelas do banco relacional
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API REST para Gestão de Matrículas Acadêmicas Universitárias com controle rigoroso de regras de negócio.",
    lifespan=lifespan,
)

# Configuração de CORS para permitir consumo frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusão dos roteadores
app.include_router(alunos_router)
app.include_router(disciplinas_router)
app.include_router(turmas_router)
app.include_router(matriculas_router)
app.include_router(historico_router)
app.include_router(relatorios_router)


@app.get("/", tags=["Status"])
def root():
    return {
        "status": "online",
        "sistema": settings.PROJECT_NAME,
        "versao": settings.VERSION,
        "docs": "/docs",
        "redoc": "/redoc"
    }
