from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
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
    # Inicializa as tabelas no banco de dados relacional
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="API de Gestão de Biblioteca Universitária",
    description=(
        "API REST completa para gerenciamento de biblioteca universitária, "
        "com controle de usuários, acervo de livros e exemplares, empréstimos, "
        "renovações, filas de reserva, multas automatizadas e relatórios gerenciais."
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


# Registra os roteadores
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
        "mensagem": "API de Gestão de Biblioteca Universitária está operacional.",
        "versao": "1.0.0",
        "documentacao": "/docs",
    }
