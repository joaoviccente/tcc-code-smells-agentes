from app.routers.clientes import router as clientes_router
from app.routers.contas import router as contas_router
from app.routers.cartoes import router as cartoes_router
from app.routers.transacoes import router as transacoes_router
from app.routers.faturas import router as faturas_router
from app.routers.tarifas import router as tarifas_router
from app.routers.relatorios import router as relatorios_router

__all__ = [
    "clientes_router",
    "contas_router",
    "cartoes_router",
    "transacoes_router",
    "faturas_router",
    "tarifas_router",
    "relatorios_router",
]
