from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import Base, engine
from app.routers import (
    cartoes_router,
    clientes_router,
    contas_router,
    faturas_router,
    relatorios_router,
    rotinas_router,
    tarifas_router,
    transacoes_router,
)

# Criação das tabelas no banco de dados
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API RESTful para gestão bancária de contas correntes, transações, cartões, faturas e tarifas.",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Tratamento customizado para erros de validação de schemas Pydantic (422)."""
    erros = []
    for error in exc.errors():
        loc = " -> ".join(str(l) for l in error.get("loc", []))
        erros.append({
            "campo": loc,
            "mensagem": error.get("msg"),
            "tipo": error.get("type"),
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "erro": "Dados de entrada inválidos",
            "detalhes": erros,
        },
    )


@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "online",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


# Inclusão dos roteadores
app.include_router(clientes_router)
app.include_router(contas_router)
app.include_router(cartoes_router)
app.include_router(transacoes_router)
app.include_router(faturas_router)
app.include_router(tarifas_router)
app.include_router(relatorios_router)
app.include_router(rotinas_router)
