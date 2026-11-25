from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import (
    alunos_router,
    disciplinas_router,
    turmas_router,
    matriculas_router,
    historicos_router,
    relatorios_router
)

# Create tables in the relational database
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="""
API REST para Gestão de Matrículas Acadêmicas de uma Universidade.

### Regras e Funcionalidades Principais:
- **Entidades**: Aluno, Disciplina, Turma, Matrícula, Pré-Requisito e Histórico.
- **Categorias de Aluno**: Graduação, Pós e Especial (créditos máximos, prazos e trancamentos).
- **Regras de Negócio**:
  1. Matrícula restrita a alunos ativos, com pré-requisitos cumpridos e respeitando o teto de créditos.
  2. Fila de espera ordenada por prioridade de categoria e data, com 48h para confirmação após liberação de vaga.
  3. Três reprovações na mesma disciplina impedem nova matrícula.
  4. Trancamento permitido apenas no prazo e respeitando o limite de trancamentos da categoria. Cancelamento fora do prazo registra reprovação por falta.
  5. Turma com menos de 5 confirmações ao fim do período de matrícula é cancelada.
  6. Conflito de horários em turmas do mesmo semestre é negado.
  7. Três trancamentos no mesmo semestre alteram situação do aluno para 'trancado' e cancelam demais confirmações.
- **Relatórios**:
  - Disciplinas mais procuradas no semestre.
  - Taxa de reprovação por disciplina.
  - Ocupação das turmas por departamento.
    """,
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(alunos_router)
app.include_router(disciplinas_router)
app.include_router(turmas_router)
app.include_router(matriculas_router)
app.include_router(historicos_router)
app.include_router(relatorios_router)

@app.get("/", tags=["Healthcheck"])
def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "docs": "/docs"
    }
