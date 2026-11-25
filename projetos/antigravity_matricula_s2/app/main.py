"""Ponto de entrada principal da aplicação FastAPI de Gestão de Matrículas Acadêmicas."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
import app.models  # Garante que todos os modelos ORM estejam registrados no Base
from app.routers import (
    alunos_router,
    disciplinas_router,
    turmas_router,
    matriculas_router,
    historico_router,
    relatorios_router,
    lista_espera_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa as tabelas do banco de dados relacional
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="API de Gestão de Matrículas Acadêmicas",
    description="""
API REST em Python para gestão de matrículas acadêmicas de uma universidade.

### Entidades
- **Aluno**: nome, matrícula, e-mail, categoria (graduação, pós ou especial), situação (ativo, trancado ou jubilado).
- **Disciplina**: código, nome, número de créditos, carga horária, departamento.
- **Turma**: pertence a uma disciplina, com semestre, professor, número de vagas, horário e estado (aberta, lotada, cancelada, encerrada).
- **Matrícula**: aluno, turma, data, estado (solicitada, confirmada, lista_de_espera, cancelada, trancada).
- **Pré-Requisito**: liga uma disciplina a outra disciplina exigida.
- **Histórico**: aluno, disciplina, semestre, nota e situação (aprovado, reprovado, trancado).

### Regras por Categoria de Aluno
- **Graduação**: máximo de 28 créditos por semestre; até 2 trancamentos por disciplina; prazo de cancelamento de 15 dias; prioridade média na lista de espera.
- **Pós**: máximo de 16 créditos por semestre; 1 trancamento por disciplina; prazo de cancelamento de 30 dias; prioridade alta na lista de espera.
- **Especial**: máximo de 8 créditos por semestre; nenhum trancamento permitido; prazo de cancelamento de 7 dias; prioridade baixa na lista de espera.

### Regras de Negócio Implementadas
1. A matrícula só é permitida a aluno ativo, aprovado em todos os pré-requisitos e sem ultrapassar o limite de créditos do semestre.
2. Turma lotada gera lista de espera ordenada por prioridade da categoria e data. Ao liberar vaga, o 1º tem 48h para confirmar; esgotado o prazo, passa ao próximo.
3. Aluno reprovado 3 vezes na mesma disciplina é impedido de se matricular nela novamente.
4. Trancamento só permitido dentro do prazo da categoria e respeitando o limite de trancamentos. Fora do prazo, registra reprovação por falta.
5. Turma com menos de 5 matrículas confirmadas ao fim do período é cancelada (e suas matrículas canceladas).
6. Matrícula com conflito de horário com turma já confirmada é negada.
7. Aluno com 3 trancamentos no semestre passa à situação 'trancado' e tem suas matrículas confirmadas canceladas.
    """,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusão dos roteadores
app.include_router(alunos_router)
app.include_router(disciplinas_router)
app.include_router(turmas_router)
app.include_router(matriculas_router)
app.include_router(historico_router)
app.include_router(relatorios_router)
app.include_router(lista_espera_router)


@app.get("/", tags=["Health"])
def root():
    return {
        "status": "online",
        "api": "Gestão de Matrículas Acadêmicas",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}
