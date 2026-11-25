from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.database import engine, Base
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
    # Criar tabelas no banco de dados se não existirem
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="API de Gestão de Contas Correntes",
    description=(
        "API REST para gerenciamento bancário completo: Clientes, Contas, Transações, Cartões, "
        "Faturas, Tarifas e Relatórios gerenciais com regras por categoria de cliente."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# Tratador personalizado para validações Pydantic retornando 422 legível
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    detalhes = []
    for err in exc.errors():
        campo = " -> ".join([str(loc) for loc in err["loc"]])
        mensagem = err["msg"]
        detalhes.append({"campo": campo, "mensagem": mensagem})

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "erro": "Dados de entrada inválidos",
            "detalhes": detalhes,
        },
    )


# Inclusão dos roteadores
app.include_router(clientes_router)
app.include_router(contas_router)
app.include_router(cartoes_router)
app.include_router(transacoes_router)
app.include_router(faturas_router)
app.include_router(tarifas_router)
app.include_router(relatorios_router)
app.include_router(rotinas_router)


@app.get("/", tags=["Status"])
def root():
    return {
        "status": "online",
        "servico": "API Bancária - Gestão de Contas Correntes",
        "docs": "/docs",
        "redoc": "/redoc",
    }
