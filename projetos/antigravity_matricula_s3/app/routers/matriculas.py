from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.matricula import Matricula
from app.models.enums import EstadoMatricula
from app.schemas.matricula import MatriculaCreate, MatriculaAction, MatriculaResponse
from app.services.matricula_service import MatriculaService
from app.services.turma_service import TurmaService

router = APIRouter(prefix="/matriculas", tags=["Matrículas"])

@router.post("", response_model=MatriculaResponse, status_code=status.HTTP_201_CREATED)
def solicitar_matricula(payload: MatriculaCreate, db: Session = Depends(get_db)):
    """
    Solicitar matrícula em uma turma:
    - Valida aluno ativo
    - Valida aprovação em todos os pré-requisitos no histórico
    - Valida limite de créditos da categoria no semestre
    - Valida se aluno foi reprovado 3 vezes na disciplina
    - Valida conflito de horários com turmas já confirmadas
    - Se houver vaga, matrícula é confirmada diretamente
    - Se a turma estiver lotada, matrícula entra na lista de espera
    """
    matricula = MatriculaService.solicitar_matricula(db, payload.aluno_id, payload.turma_id)
    TurmaService.enriquecer_turma(db, matricula.turma)
    return matricula

@router.post("/{id}/confirmar", response_model=MatriculaResponse)
def confirmar_matricula(
    id: int,
    action: Optional[MatriculaAction] = None,
    db: Session = Depends(get_db)
):
    """
    Confirmar matrícula (ex: aluno promovido da fila de espera que tem 48 horas para confirmar).
    """
    ref_time = action.data_referencia if action else None
    matricula = MatriculaService.confirmar_matricula(db, id, ref_time)
    TurmaService.enriquecer_turma(db, matricula.turma)
    return matricula

@router.post("/{id}/cancelar", response_model=MatriculaResponse)
def cancelar_matricula(
    id: int,
    action: Optional[MatriculaAction] = None,
    db: Session = Depends(get_db)
):
    """
    Cancelar matrícula:
    - Dentro do prazo da categoria: cancela normalmente e libera vaga
    - Fora do prazo da categoria: cancela e registra 'reprovação por falta' no histórico
    - Libera a vaga e repassa ao primeiro da lista de espera (prazo de 48h)
    """
    ref_time = action.data_referencia if action else None
    matricula = MatriculaService.cancelar_matricula(db, id, ref_time)
    TurmaService.enriquecer_turma(db, matricula.turma)
    return matricula

@router.post("/{id}/trancar", response_model=MatriculaResponse)
def trancar_matricula(
    id: int,
    action: Optional[MatriculaAction] = None,
    db: Session = Depends(get_db)
):
    """
    Trancar matrícula:
    - Permitido apenas dentro do prazo de cancelamento da categoria
    - Respeita o limite de trancamentos por disciplina da categoria
    - Registra trancamento no histórico
    - Se acumular 3 trancamentos no semestre: aluno passa à situação trancado e cancela confirmadas
    - Libera vaga e repassa ao primeiro da lista de espera
    """
    ref_time = action.data_referencia if action else None
    matricula = MatriculaService.trancar_matricula(db, id, ref_time)
    TurmaService.enriquecer_turma(db, matricula.turma)
    return matricula

@router.get("", response_model=List[MatriculaResponse])
def listar_matriculas(
    aluno_id: Optional[int] = Query(None),
    turma_id: Optional[int] = Query(None),
    estado: Optional[EstadoMatricula] = Query(None),
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
    for m in matriculas:
        TurmaService.enriquecer_turma(db, m.turma)
    return matriculas

@router.get("/{id}", response_model=MatriculaResponse)
def obter_matricula(id: int, db: Session = Depends(get_db)):
    matricula = db.query(Matricula).filter(Matricula.id == id).first()
    if not matricula:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Matrícula {id} não encontrada")
    TurmaService.enriquecer_turma(db, matricula.turma)
    return matricula

@router.post("/processar-expiradas", response_model=List[MatriculaResponse])
def processar_expiradas(
    action: Optional[MatriculaAction] = None,
    turma_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Processa vagas da lista de espera cujo prazo de confirmação de 48h expirou.
    A matrícula expirada é cancelada e a vez passa para o próximo da fila.
    """
    ref_time = action.data_referencia if action else None
    expiradas = MatriculaService.processar_expirados_fila(db, turma_id, ref_time)
    for m in expiradas:
        TurmaService.enriquecer_turma(db, m.turma)
    return expiradas
