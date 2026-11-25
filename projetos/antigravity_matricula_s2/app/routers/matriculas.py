"""Rotas REST para solicitação, confirmação, cancelamento e trancamento de matrículas."""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.matricula import Matricula
from app.models.aluno import Aluno
from app.schemas.matricula import (
    MatriculaSolicitar,
    MatriculaResponse,
)
from app.services.matricula_service import (
    solicitar_matricula as service_solicitar,
    confirmar_matricula as service_confirmar,
    cancelar_matricula as service_cancelar,
    trancar_matricula as service_trancar,
)

router = APIRouter(prefix="/matriculas", tags=["Matrículas"])


def formatar_matricula_response(m: Matricula) -> MatriculaResponse:
    return MatriculaResponse(
        id=m.id,
        aluno_id=m.aluno_id,
        turma_id=m.turma_id,
        data=m.data,
        data_limite_confirmacao=m.data_limite_confirmacao,
        estado=m.estado,
        aluno_nome=m.aluno.nome if m.aluno else None,
        aluno_matricula=m.aluno.matricula if m.aluno else None,
        disciplina_codigo=m.turma.disciplina.codigo if m.turma and m.turma.disciplina else None,
        disciplina_nome=m.turma.disciplina.nome if m.turma and m.turma.disciplina else None,
        turma_semestre=m.turma.semestre if m.turma else None,
        turma_horario=m.turma.horario if m.turma else None,
    )


def parse_param_datetime(dt_val: Optional[str]) -> Optional[datetime]:
    if not dt_val:
        return None
    s = str(dt_val).strip()
    if " " in s and "+" not in s and ("T" in s or "-" in s):
        parts = s.rsplit(" ", 1)
        if len(parts) == 2 and (":" in parts[1] or parts[1].isdigit()):
            s = f"{parts[0]}+{parts[1]}"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        from datetime import timezone
        try:
            from dateutil import parser
            return parser.parse(s)
        except Exception:
            return None


@router.post("/solicitar", response_model=MatriculaResponse, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=MatriculaResponse, status_code=status.HTTP_201_CREATED)
def solicitar_matricula(payload: MatriculaSolicitar, db: Session = Depends(get_db)):
    """
    Solicita matrícula para um aluno em uma turma.
    Executa todas as regras de negócio:
    - Regra 1: Aluno ativo, pré-requisitos cumpridos, limite de créditos.
    - Regra 2: Turma lotada -> entra em lista de espera.
    - Regra 3: Aluno reprovado 3 vezes na disciplina é impedido.
    - Regra 6: Conflito de horário negado.
    """
    matricula = service_solicitar(
        db=db,
        aluno_id=payload.aluno_id,
        turma_id=payload.turma_id,
        data=payload.data,
        auto_confirm=payload.auto_confirm,
    )
    return formatar_matricula_response(matricula)


@router.post("/{id}/confirmar", response_model=MatriculaResponse)
def confirmar_matricula(id: int, db: Session = Depends(get_db)):
    """
    Confirma uma matrícula solicitada ou liberada da lista de espera (Regra 2).
    """
    matricula = service_confirmar(db=db, matricula_id=id)
    return formatar_matricula_response(matricula)


@router.post("/{id}/cancelar", response_model=MatriculaResponse)
def cancelar_matricula(
    id: int,
    data_cancelamento: Optional[str] = Query(None, description="Data/hora do cancelamento (ISO 8601)"),
    db: Session = Depends(get_db)
):
    """
    Cancela uma matrícula.
    - Se confirmada e fora do prazo de cancelamento da categoria: registra reprovação por falta (Regra 4).
    - Libera vaga e notifica o próximo da fila de espera com 48h (Regra 2).
    """
    dt_parsed = parse_param_datetime(data_cancelamento)
    matricula = service_cancelar(
        db=db,
        matricula_id=id,
        data_cancelamento=dt_parsed,
    )
    return formatar_matricula_response(matricula)


@router.post("/{id}/trancar", response_model=MatriculaResponse)
def trancar_matricula(
    id: int,
    data_trancamento: Optional[str] = Query(None, description="Data/hora do trancamento (ISO 8601)"),
    db: Session = Depends(get_db)
):
    """
    Tranca uma matrícula confirmada.
    - Regra 4: Permitido apenas dentro do prazo de cancelamento da categoria e respeitando
      o limite de trancamentos por disciplina (Graduação: até 2, Pós: 1, Especial: 0).
      Fora do prazo, registra reprovação por falta no histórico.
    - Regra 7: Se acumular 3 trancamentos no semestre, o aluno passa à situação trancado,
      e todas as suas matrículas confirmadas são canceladas.
    """
    dt_parsed = parse_param_datetime(data_trancamento)
    matricula = service_trancar(
        db=db,
        matricula_id=id,
        data_trancamento=dt_parsed,
    )
    return formatar_matricula_response(matricula)


@router.get("/aluno/{aluno_id}", response_model=List[MatriculaResponse])
def listar_matriculas_por_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """
    Lista todas as matrículas de um aluno.
    """
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado")

    matriculas = db.query(Matricula).filter(Matricula.aluno_id == aluno_id).all()
    return [formatar_matricula_response(m) for m in matriculas]


@router.get("", response_model=List[MatriculaResponse])
def listar_matriculas(
    aluno_id: Optional[int] = None,
    turma_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Lista matrículas com filtros opcionais por aluno ou turma."""
    query = db.query(Matricula)
    if aluno_id:
        query = query.filter(Matricula.aluno_id == aluno_id)
    if turma_id:
        query = query.filter(Matricula.turma_id == turma_id)

    matriculas = query.all()
    return [formatar_matricula_response(m) for m in matriculas]


@router.get("/{id}", response_model=MatriculaResponse)
def obter_matricula(id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma matrícula por ID."""
    matricula = db.query(Matricula).filter(Matricula.id == id).first()
    if not matricula:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matrícula não encontrada")
    return formatar_matricula_response(matricula)
