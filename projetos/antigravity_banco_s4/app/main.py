from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.config import settings
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
    # Cria as tabelas no banco de dados na inicialização
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
API REST em Python para Gestão de Contas Correntes Bancárias.

### Regras de Negócio Implementadas:
1. **Saque e Transferência:** Permitidos apenas em conta ativa, de cliente ativo, respeitando o limite diário acumulado e limite por operação da categoria.
2. **Limite de Crédito:** O saldo pode ficar negativo até o limite de crédito contratado. Operações abaixo disso são recusadas.
3. **Isenção e Tarifação de Transferências:** Entre contas do mesmo cliente são 100% isentas. Para contas de clientes distintos, consomem a franquia mensal da categoria e geram tarifas após esgotada a franquia.
4. **Estorno de Transações:** Estorno permitido em até 24 horas, revertendo saldos e registrando nova transação do tipo estorno.
5. **Atraso de Faturas:** Acúmulo de juros por categoria ao vencer sem pagamento integral. Bloqueio automático do cartão após 10 dias de atraso.
6. **Saldo Negativo Prolongado:** Contas com saldo negativo por mais de 30 dias bloqueiam o cliente e todos os seus cartões vinculados.
7. **Encerramento de Conta:** Exige saldo exatamente zero e nenhuma fatura em aberto. Cancela automaticamente todos os cartões vinculados.
    """,
    lifespan=lifespan,
)

# Registra os roteadores
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
        "projeto": settings.PROJECT_NAME,
        "versao": settings.VERSION,
        "docs": "/docs",
    }


@app.get("/health", tags=["Status"])
def health_check():
    return {"status": "healthy"}
