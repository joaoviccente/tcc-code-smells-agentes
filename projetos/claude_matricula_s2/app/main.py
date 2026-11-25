from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import services
from app.database import Base, engine, get_db
from app.errors import DomainError
from app.routers import alunos, disciplinas, matriculas, relatorios, turmas
from app.schemas import EncerramentoPeriodoOut, Semestre


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="API de Gestao de Matriculas Academicas",
    version="1.0.0",
    description="Alunos, disciplinas, turmas, matriculas, lista de espera, historico e relatorios.",
)


@app.exception_handler(DomainError)
def _domain_error(_: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(IntegrityError)
def _integrity_error(_: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "violacao de integridade dos dados"})


administracao = APIRouter(tags=["Administracao"])


@administracao.post("/semestres/{semestre}/encerrar-periodo-matricula", response_model=EncerramentoPeriodoOut)
def encerrar_periodo(semestre: Semestre, db: Session = Depends(get_db)):
    """Fim do periodo de matricula: cancela turmas com menos de 5 matriculas confirmadas."""
    return services.encerrar_periodo(db, semestre)


@administracao.post("/lista-espera/processar-expiracoes")
def processar_expiracoes(db: Session = Depends(get_db)):
    """Cancela ofertas de vaga cujo prazo de 48h expirou e passa a vez ao proximo (pode ser agendado)."""
    return {"matriculas_expiradas": services.processar_todas_expiracoes(db)}


for r in (alunos.router, disciplinas.router, turmas.router, matriculas.router, relatorios.router, administracao):
    app.include_router(r)
