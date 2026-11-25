from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Matricula
from ..schemas import MatriculaCreate, MatriculaOut, ResultadoOperacao
from ..servicos import (
    cancelar_matricula,
    confirmar_matricula,
    obter_ou_404,
    preencher_posicao,
    solicitar_matricula,
    trancar_matricula,
)

router = APIRouter(prefix="/matriculas", tags=["Matriculas"])


@router.post(
    "",
    response_model=MatriculaOut,
    status_code=201,
    summary="Solicitar matricula (entra em lista de espera se a turma estiver lotada)",
)
def solicitar(dados: MatriculaCreate, db: Session = Depends(get_db)):
    return solicitar_matricula(db, dados.aluno_id, dados.turma_id)


@router.get("/{matricula_id}", response_model=MatriculaOut)
def obter(matricula_id: int, db: Session = Depends(get_db)):
    m = obter_ou_404(db, Matricula, matricula_id, "Matricula")
    return preencher_posicao(db, [m])[0]


@router.post("/{matricula_id}/confirmar", response_model=MatriculaOut)
def confirmar(matricula_id: int, db: Session = Depends(get_db)):
    return confirmar_matricula(db, matricula_id)


@router.post("/{matricula_id}/cancelar", response_model=ResultadoOperacao)
def cancelar(matricula_id: int, db: Session = Depends(get_db)):
    m, avisos = cancelar_matricula(db, matricula_id)
    return ResultadoOperacao(matricula=MatriculaOut.model_validate(m), avisos=avisos)


@router.post("/{matricula_id}/trancar", response_model=ResultadoOperacao)
def trancar(matricula_id: int, db: Session = Depends(get_db)):
    m, avisos = trancar_matricula(db, matricula_id)
    return ResultadoOperacao(matricula=MatriculaOut.model_validate(m), avisos=avisos)
