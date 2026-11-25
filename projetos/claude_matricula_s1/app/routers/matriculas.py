from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.models import Matricula
from app.schemas import CancelamentoOut, EncerramentoPeriodoOut, MatriculaCreate, MatriculaOut

router = APIRouter(tags=["matriculas"])


@router.post("/matriculas", response_model=MatriculaOut, status_code=status.HTTP_201_CREATED,
             summary="Solicitar matricula (entra em lista de espera se a turma estiver lotada)")
def solicitar(dados: MatriculaCreate, db: Session = Depends(get_db)):
    m = services.solicitar(db, dados.aluno_id, dados.turma_id)
    db.commit()
    return m


@router.get("/matriculas/{matricula_id}", response_model=MatriculaOut)
def obter(matricula_id: int, db: Session = Depends(get_db)):
    services.processar_prazos(db)
    db.commit()
    return services.obter(db, Matricula, matricula_id, "matricula")


@router.post("/matriculas/{matricula_id}/confirmar", response_model=MatriculaOut)
def confirmar(matricula_id: int, db: Session = Depends(get_db)):
    m = services.confirmar(db, matricula_id)
    db.commit()
    return m


@router.post("/matriculas/{matricula_id}/cancelar", response_model=CancelamentoOut)
def cancelar(matricula_id: int, db: Session = Depends(get_db)):
    m, reprovacao = services.cancelar(db, matricula_id)
    db.commit()
    return CancelamentoOut(matricula=MatriculaOut.model_validate(m), reprovacao_por_falta=reprovacao)


@router.post("/matriculas/{matricula_id}/trancar", response_model=MatriculaOut)
def trancar(matricula_id: int, db: Session = Depends(get_db)):
    m = services.trancar(db, matricula_id)
    db.commit()
    return m


@router.post("/semestres/{semestre}/encerrar-periodo-matricula", response_model=EncerramentoPeriodoOut,
             tags=["administracao"])
def encerrar_periodo(semestre: str = Path(pattern=r"^\d{4}\.[12]$"), db: Session = Depends(get_db)):
    resultado = services.encerrar_periodo_matricula(db, semestre)
    db.commit()
    return resultado


@router.post("/admin/processar-prazos", tags=["administracao"],
             summary="Expira ofertas de vaga nao confirmadas em 48h (tambem ocorre automaticamente)")
def processar_prazos(db: Session = Depends(get_db)):
    n = services.processar_prazos(db)
    db.commit()
    return {"matriculas_expiradas": n}
