from app.routers.usuarios import router as usuarios_router
from app.routers.livros import router as livros_router
from app.routers.exemplares import router as exemplares_router
from app.routers.emprestimos import router as emprestimos_router
from app.routers.reservas import router as reservas_router
from app.routers.multas import router as multas_router
from app.routers.relatorios import router as relatorios_router

__all__ = [
    "usuarios_router",
    "livros_router",
    "exemplares_router",
    "emprestimos_router",
    "reservas_router",
    "multas_router",
    "relatorios_router",
]
