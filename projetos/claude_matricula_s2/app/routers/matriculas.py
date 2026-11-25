from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.models import Matricula
from app.schemas import CancelamentoOut, MatriculaCreate, MatriculaOut, TrancamentoOut

router = APIRouter(prefix="/matriculas", tags=["Matriculas"])


def matricula_out(db: Session, m: Matricula) -> MatriculaOut:
    out = MatriculaOut.model_validate(m)
    out.posicao_fila = services.posicao_na_fila(db, m)
    return out


@router.post("", response_model=MatriculaOut, status_code=status.HTTP_201_CREATED,
             summary="Solicitar matricula",
             description="Cria a matricula como 'solicitada' se houver vaga, ou em 'lista_de_espera' se a "
                         "turma estiver lotada.")
def solicitar(dados: MatriculaCreate, db: Session = Depends(get_db)):
    return matricula_out(db, services.solicitar(db, dados.aluno_id, dados.turma_id))


@router.get("/{matricula_id}", response_model=MatriculaOut)
def obter(matricula_id: int, db: Session = Depends(get_db)):
    m = services.obter(db, Matricula, matricula_id, "matricula")
    if services.processar_expiracoes(db, m.turma):
        db.commit()
    return matricula_out(db, m)


@router.post("/{matricula_id}/confirmar", response_model=MatriculaOut)
def confirmar(matricula_id: int, db: Session = Depends(get_db)):
    return matricula_out(db, services.confirmar(db, matricula_id))


@router.post("/{matricula_id}/cancelar", response_model=CancelamentoOut)
def cancelar(matricula_id: int, db: Session = Depends(get_db)):
    m, reprovacao = services.cancelar(db, matricula_id)
    return CancelamentoOut(matricula=matricula_out(db, m), reprovacao_por_falta=reprovacao)


@router.post("/{matricula_id}/trancar", response_model=TrancamentoOut)
def trancar(matricula_id: int, db: Session = Depends(get_db)):
    m, n, trancado = services.trancar(db, matricula_id)
    return TrancamentoOut(matricula=matricula_out(db, m), trancamentos_no_semestre=n, aluno_trancado=trancado)
