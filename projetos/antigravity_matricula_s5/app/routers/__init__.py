from app.routers.alunos import router as alunos_router
from app.routers.disciplinas import router as disciplinas_router
from app.routers.turmas import router as turmas_router
from app.routers.matriculas import router as matriculas_router
from app.routers.historico import router as historico_router
from app.routers.relatorios import router as relatorios_router

__all__ = [
    "alunos_router",
    "disciplinas_router",
    "turmas_router",
    "matriculas_router",
    "historico_router",
    "relatorios_router",
]
