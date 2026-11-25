from app.routers.alunos import router as alunos_router
from app.routers.disciplinas import router as disciplinas_router
from app.routers.turmas import router as turmas_router
from app.routers.matriculas import router as matriculas_router
from app.routers.historicos import router as historicos_router
from app.routers.relatorios import router as relatorios_router

__all__ = [
    "alunos_router",
    "disciplinas_router",
    "turmas_router",
    "matriculas_router",
    "historicos_router",
    "relatorios_router",
]
