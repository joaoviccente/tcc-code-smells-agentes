from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.matricula import Matricula
from app.models.enums import EstadoMatricula
from app.schemas.matricula import (
    MatriculaSolicitacao,
    MatriculaActionRequest,
    MatriculaResponse,
    MatriculaDetailResponse,
)
from app.services.matricula_service import (
    solicitar_matricula,
    confirmar_matricula,
    cancelar_matricula,
    trancar_matricula,
    get_waitlist_ordered,
)
from app.services.turma_service import get_turma_with_details

router = APIRouter(prefix="/matriculas", tags=["Matrículas"])


@router.post("/solicitar", response_model=MatriculaResponse, status_code=status.HTTP_201_CREATED)
def acao_solicitar_matricula(
    payload: MatriculaSolicitacao,
    db: Session = Depends(get_db)
):
    """
    Solicita matrícula para um aluno em uma turma.
    Aplica as validações:
    - Regra 1: Aluno ativo, pré-requisitos cumpridos com aprovação, limite de créditos da categoria.
    - Regra 2: Se turma lotada, vai para lista de espera priorizada.
    - Regra 3: Impede matrícula se o aluno já tiver 3 reprovações nesta disciplina.
    - Regra 6: Impede matrícula se houver conflito de horário com turma já confirmada.
    """
    matricula = solicitar_matricula(
        db=db,
        aluno_id=payload.aluno_id,
        turma_id=payload.turma_id,
        auto_confirm=payload.auto_confirm
    )
    return matricula


@router.post("/{matricula_id}/confirmar", response_model=MatriculaResponse)
def acao_confirmar_matricula(
    matricula_id: int,
    payload: Optional[MatriculaActionRequest] = None,
    db: Session = Depends(get_db)
):
    """
    REGRA 2: Confirma a matrícula de um aluno.
    Usado quando uma vaga foi liberada na lista de espera (dentro do prazo de 48h)
    ou quando a matrícula estava no estado 'solicitada'.
    Esgotado o prazo de 48h, a matrícula é cancelada e a vez é passada ao próximo.
    """
    data_ref = payload.data_referencia if payload else None
    return confirmar_matricula(db=db, matricula_id=matricula_id, data_ref=data_ref)


@router.post("/{matricula_id}/cancelar")
def acao_cancelar_matricula(
    matricula_id: int,
    payload: Optional[MatriculaActionRequest] = None,
    db: Session = Depends(get_db)
):
    """
    REGRA 4: Cancela a matrícula.
    Dentro do prazo da categoria (Graduação: 15 dias, Pós: 30 dias, Especial: 7 dias),
    o cancelamento é limpo. Fora do prazo, registra reprovação por falta no histórico acadêmico.
    Se liberar vaga, a lista de espera é acionada automaticamente (48h para o primeiro da fila).
    """
    data_ref = payload.data_referencia if payload else None
    mat, msg = cancelar_matricula(db=db, matricula_id=matricula_id, data_ref=data_ref)
    return {
        "matricula_id": mat.id,
        "estado": mat.estado.value,
        "mensagem": msg
    }


@router.post("/{matricula_id}/trancar")
def acao_trancar_matricula(
    matricula_id: int,
    payload: Optional[MatriculaActionRequest] = None,
    db: Session = Depends(get_db)
):
    """
    REGRA 4 e REGRA 7: Tranca a matrícula em uma disciplina.
    - Permitido apenas dentro do prazo de cancelamento da categoria.
    - Respeita o limite de trancamentos por disciplina (Graduação: 2, Pós: 1, Especial: 0).
    - Regra 7: Se o aluno acumular 3 trancamentos no semestre, passa para situação 'trancado'
      e todas as suas outras matrículas confirmadas são automaticamente canceladas.
    - Libera vaga para o próximo da lista de espera (48h).
    """
    data_ref = payload.data_referencia if payload else None
    mat, msg = trancar_matricula(db=db, matricula_id=matricula_id, data_ref=data_ref)
    return {
        "matricula_id": mat.id,
        "estado": mat.estado.value,
        "mensagem": msg
    }


@router.get("/aluno/{aluno_id}", response_model=List[MatriculaResponse])
def listar_matriculas_por_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """Lista todas as matrículas de um aluno específico."""
    matriculas = db.query(Matricula).filter(Matricula.aluno_id == aluno_id).all()
    return matriculas


@router.get("", response_model=List[MatriculaResponse])
def listar_matriculas(
    aluno_id: Optional[int] = None,
    turma_id: Optional[int] = None,
    estado: Optional[EstadoMatricula] = None,
    db: Session = Depends(get_db)
):
    """Lista matrículas com filtros opcionais por aluno, turma e estado."""
    query = db.query(Matricula)
    if aluno_id:
        query = query.filter(Matricula.aluno_id == aluno_id)
    if turma_id:
        query = query.filter(Matricula.turma_id == turma_id)
    if estado:
        query = query.filter(Matricula.estado == estado)
    return query.all()


@router.get("/{matricula_id}", response_model=MatriculaDetailResponse)
def obter_matricula(matricula_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes completos de uma matrícula."""
    matricula = db.query(Matricula).filter(Matricula.id == matricula_id).first()
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matrícula com ID {matricula_id} não encontrada."
        )

    # Detalhar turma
    turma_detalhada = get_turma_with_details(db, matricula.turma_id)
    matricula.turma = turma_detalhada

    # Se estiver em lista de espera, calcular posição
    if matricula.estado == EstadoMatricula.LISTA_DE_ESPERA:
        fila = get_waitlist_ordered(db, matricula.turma_id)
        for idx, m in enumerate(fila, start=1):
            if m.id == matricula.id:
                matricula.posicao_fila = idx
                break

    return matricula
