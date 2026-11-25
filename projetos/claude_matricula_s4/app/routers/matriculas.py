from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import servicos as sv
from app.database import get_db
from app.models import Matricula
from app.routers.comum import matricula_saida
from app.schemas import (CancelamentoSaida, MatriculaCriar, MatriculaSaida,
                         TrancamentoSaida)

router = APIRouter(prefix="/matriculas", tags=["Matriculas"])


@router.post("", response_model=MatriculaSaida, status_code=status.HTTP_201_CREATED,
             summary="Solicitar matricula (entra em lista de espera se a turma estiver lotada)")
def solicitar(dados: MatriculaCriar, db: Session = Depends(get_db)):
    return matricula_saida(db, sv.solicitar(db, dados.aluno_id, dados.turma_id))


@router.get("/{matricula_id}", response_model=MatriculaSaida)
def obter(matricula_id: int, db: Session = Depends(get_db)):
    m = sv.obter(db, Matricula, matricula_id, "Matricula")
    sv.processar_expiracoes(db, m.turma)
    db.commit()
    return matricula_saida(db, m)


@router.post("/{matricula_id}/confirmar", response_model=MatriculaSaida)
def confirmar(matricula_id: int, db: Session = Depends(get_db)):
    return matricula_saida(db, sv.confirmar(db, matricula_id))


@router.post("/{matricula_id}/cancelar", response_model=CancelamentoSaida)
def cancelar(matricula_id: int, db: Session = Depends(get_db)):
    m, dentro, reprov = sv.cancelar(db, matricula_id)
    return CancelamentoSaida(matricula=matricula_saida(db, m), dentro_do_prazo=dentro,
                             reprovacao_registrada=reprov)


@router.post("/{matricula_id}/trancar", response_model=TrancamentoSaida)
def trancar(matricula_id: int, db: Session = Depends(get_db)):
    r = sv.trancar(db, matricula_id)
    r["matricula"] = matricula_saida(db, r["matricula"])
    return TrancamentoSaida(**r)
