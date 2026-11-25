from typing import List, Optional
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.matricula import (
    MatriculaSolicitarRequest,
    MatriculaAcaoRequest,
    MatriculaResponse,
)
from app.models.matricula import Matricula
from app.services import matricula_service

router = APIRouter(prefix="/matriculas", tags=["Matrículas"])


def format_matricula_response(m) -> MatriculaResponse:
    return MatriculaResponse(
        id=m.id,
        aluno_id=m.aluno_id,
        turma_id=m.turma_id,
        data=m.data,
        estado=m.estado,
        data_oferta_vaga=m.data_oferta_vaga,
        aluno_nome=m.aluno.nome if m.aluno else None,
        aluno_categoria=m.aluno.categoria if m.aluno else None,
        disciplina_codigo=m.turma.disciplina.codigo if m.turma and m.turma.disciplina else None,
        disciplina_nome=m.turma.disciplina.nome if m.turma and m.turma.disciplina else None,
        semestre=m.turma.semestre if m.turma else None,
    )


@router.post("", response_model=MatriculaResponse, status_code=status.HTTP_201_CREATED)
@router.post("/solicitar", response_model=MatriculaResponse, status_code=status.HTTP_201_CREATED)
def solicitar_matricula(data: MatriculaSolicitarRequest, db: Session = Depends(get_db)):
    """
    Solicitar matrícula em uma turma.
    - Se houver vaga: matrícula é confirmada.
    - Se a turma estiver lotada: entra na lista de espera ordenada por categoria e data.
    Valida pré-requisitos, limite de créditos da categoria, conflito de horários e histórico de reprovações.
    """
    matricula = matricula_service.solicitar_matricula(db, data.aluno_id, data.turma_id)
    return format_matricula_response(matricula)


@router.post("/{matricula_id}/confirmar", response_model=MatriculaResponse)
def confirmar_matricula(
    matricula_id: int,
    data: Optional[MatriculaAcaoRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Confirmar matrícula (ex: aluno chamado da lista de espera com até 48 horas para confirmar).
    """
    simulated_now = data.data_acao if data else None
    matricula = matricula_service.confirmar_matricula(db, matricula_id, simulated_now=simulated_now)
    return format_matricula_response(matricula)


@router.post("/{matricula_id}/cancelar", response_model=MatriculaResponse)
def cancelar_matricula(
    matricula_id: int,
    data: Optional[MatriculaAcaoRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Cancelar matrícula.
    Regra 4: Se o cancelamento for realizado fora do prazo da categoria do aluno
    (Graduação: 15 dias, Pós: 30 dias, Especial: 7 dias), registra reprovação por falta no histórico.
    """
    simulated_now = data.data_acao if data else None
    matricula = matricula_service.cancelar_matricula(db, matricula_id, simulated_now=simulated_now)
    return format_matricula_response(matricula)


@router.post("/{matricula_id}/trancar", response_model=MatriculaResponse)
def trancar_matricula(
    matricula_id: int,
    data: Optional[MatriculaAcaoRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Trancar matrícula na disciplina.
    Regra 4: Permitido apenas dentro do prazo de cancelamento da categoria e respeitando o limite
    de trancamentos (Graduação: até 2; Pós: 1; Especial: 0).
    Regra 7: Se acumular 3 trancamentos no mesmo semestre, o aluno passa à situação trancado
    e todas as suas matrículas confirmadas são canceladas.
    """
    simulated_now = data.data_acao if data else None
    matricula = matricula_service.trancar_matricula(db, matricula_id, simulated_now=simulated_now)
    return format_matricula_response(matricula)


@router.get("/aluno/{aluno_id}", response_model=List[MatriculaResponse])
def listar_matriculas_por_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """
    Listar matrículas por aluno.
    """
    matriculas = matricula_service.list_matriculas_por_aluno(db, aluno_id)
    return [format_matricula_response(m) for m in matriculas]


@router.get("/{matricula_id}", response_model=MatriculaResponse)
def obter_matricula(matricula_id: int, db: Session = Depends(get_db)):
    matricula = matricula_service.get_matricula_by_id(db, matricula_id)
    return format_matricula_response(matricula)


@router.get("", response_model=List[MatriculaResponse])
def listar_matriculas(
    aluno_id: Optional[int] = None,
    turma_id: Optional[int] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Matricula)
    if aluno_id:
        query = query.filter(Matricula.aluno_id == aluno_id)
    if turma_id:
        query = query.filter(Matricula.turma_id == turma_id)
    if estado:
        query = query.filter(Matricula.estado == estado)
    matriculas = query.all()
    return [format_matricula_response(m) for m in matriculas]
