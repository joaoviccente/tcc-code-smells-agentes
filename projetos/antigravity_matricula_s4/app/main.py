from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
import app.models  # Garante que todos os modelos são registrados no Base.metadata
from app.routers import alunos, disciplinas, turmas, matriculas, historicos, relatorios


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cria as tabelas do banco relacional na inicialização
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="API de Gestão de Matrículas Acadêmicas",
    description=(
        "API REST completa para gestão acadêmica e de matrículas universitárias, "
        "com suporte a controle de créditos por categoria (graduação, pós, especial), "
        "gestão dinâmica de lista de espera com prioridades e janelas de 48h, "
        "validação de pré-requisitos e histórico de reprovações, detecção de conflitos "
        "de horário, cancelamento/trancamento com prazos estritos e relatórios analíticos."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Habilitar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar rotas
app.include_router(alunos.router)
app.include_router(disciplinas.router)
app.include_router(turmas.router)
app.include_router(matriculas.router)
app.include_router(historicos.router)
app.include_router(relatorios.router)


@app.get("/", tags=["Status"])
def root():
    return {
        "sistema": "API de Gestão de Matrículas Acadêmicas",
        "status": "online",
        "versao": "1.0.0",
        "documentacao": "/docs",
        "openapi": "/openapi.json"
    }


@app.get("/health", tags=["Status"])
def health():
    return {"status": "healthy"}
