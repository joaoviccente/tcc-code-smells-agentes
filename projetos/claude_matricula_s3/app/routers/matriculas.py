from datetime import datetime

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from .. import schemas
from ..deps import db_sincronizado, obter_agora
from ..services import matriculas as svc

router = APIRouter(tags=["Matrículas"])


def _saida(db: Session, r: svc.ResultadoOperacao) -> schemas.OperacaoMatriculaOut:
    m = schemas.MatriculaOut.model_validate(r.matricula)
    m.posicao_lista_espera = svc.posicao_na_fila(db, r.matricula)
    return schemas.OperacaoMatriculaOut(
        matricula=m,
        mensagem=r.mensagem,
        reprovacao_por_falta_registrada=r.reprovacao_por_falta_registrada,
        aluno_trancado=r.aluno_trancado,
        matriculas_canceladas=r.matriculas_canceladas,
    )


@router.post(
    "/matriculas",
    response_model=schemas.OperacaoMatriculaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar matrícula (entra em lista de espera se a turma estiver lotada)",
)
def solicitar(
    dados: schemas.MatriculaCreate,
    db: Session = Depends(db_sincronizado),
    agora: datetime = Depends(obter_agora),
):
    return _saida(db, svc.solicitar(db, dados.aluno_id, dados.turma_id, agora))


@router.get("/matriculas/{matricula_id}", response_model=schemas.MatriculaOut)
def obter(matricula_id: int, db: Session = Depends(db_sincronizado)):
    m = svc.obter_matricula(db, matricula_id)
    out = schemas.MatriculaOut.model_validate(m)
    out.posicao_lista_espera = svc.posicao_na_fila(db, m)
    return out


@router.post("/matriculas/{matricula_id}/confirmar", response_model=schemas.OperacaoMatriculaOut)
def confirmar(
    matricula_id: int,
    db: Session = Depends(db_sincronizado),
    agora: datetime = Depends(obter_agora),
):
    return _saida(db, svc.confirmar(db, matricula_id, agora))


@router.post("/matriculas/{matricula_id}/cancelar", response_model=schemas.OperacaoMatriculaOut)
def cancelar(
    matricula_id: int,
    db: Session = Depends(db_sincronizado),
    agora: datetime = Depends(obter_agora),
):
    return _saida(db, svc.cancelar(db, matricula_id, agora))


@router.post("/matriculas/{matricula_id}/trancar", response_model=schemas.OperacaoMatriculaOut)
def trancar(
    matricula_id: int,
    db: Session = Depends(db_sincronizado),
    agora: datetime = Depends(obter_agora),
):
    return _saida(db, svc.trancar(db, matricula_id, agora))


@router.post(
    "/periodos/{semestre}/encerrar-matriculas",
    response_model=schemas.EncerramentoPeriodoOut,
    tags=["Período de matrícula"],
    summary="Encerra o período de matrícula e cancela turmas com menos de 5 confirmadas",
)
def encerrar_periodo(
    semestre: str = Path(pattern=schemas.SEMESTRE_REGEX),
    db: Session = Depends(db_sincronizado),
    agora: datetime = Depends(obter_agora),
):
    return svc.encerrar_periodo(db, semestre, agora)
