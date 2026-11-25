from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    # Criar tabelas se não existirem
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="API de Gestão de Biblioteca Universitária",
    description="API RESTful completa para gerenciamento de acervo, usuários, empréstimos, reservas, multas e relatórios.",
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

# Rotas sem prefixo
app.include_router(usuarios_router)
app.include_router(livros_router)
app.include_router(exemplares_router)
app.include_router(emprestimos_router)
app.include_router(reservas_router)
app.include_router(multas_router)
app.include_router(relatorios_router)

# Rotas com prefixo /api para compatibilidade total
app.include_router(usuarios_router, prefix="/api")
app.include_router(livros_router, prefix="/api")
app.include_router(exemplares_router, prefix="/api")
app.include_router(emprestimos_router, prefix="/api")
app.include_router(reservas_router, prefix="/api")
app.include_router(multas_router, prefix="/api")
app.include_router(relatorios_router, prefix="/api")


@app.get("/", tags=["Status"])
def root():
    return {
        "status": "online",
        "api": "API de Gestão de Biblioteca Universitária",
        "versao": "1.0.0",
        "documentacao": "/docs",
    }
