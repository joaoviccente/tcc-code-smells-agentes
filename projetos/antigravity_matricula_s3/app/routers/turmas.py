from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.turma import Turma
from app.models.disciplina import Disciplina
from app.models.enums import EstadoTurma
from app.schemas.turma import TurmaCreate, TurmaUpdate, TurmaResponse
from app.schemas.matricula import FilaEsperaResponse
from app.services.turma_service import TurmaService
from app.services.matricula_service import MatriculaService

router = APIRouter(prefix="/turmas", tags=["Turmas"])

@router.post("", response_model=TurmaResponse, status_code=status.HTTP_201_CREATED)
def criar_turma(payload: TurmaCreate, db: Session = Depends(get_db)):
    disciplina = db.query(Disciplina).filter(Disciplina.id == payload.disciplina_id).first()
    if not disciplina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina com ID {payload.disciplina_id} não encontrada"
        )

    turma = Turma(**payload.model_dump())
    db.add(turma)
    db.commit()
    db.refresh(turma)
    return TurmaService.enriquecer_turma(db, turma)

@router.get("", response_model=List[TurmaResponse])
def listar_turmas(
    disciplina_id: Optional[int] = Query(None),
    semestre: Optional[str] = Query(None),
    estado: Optional[EstadoTurma] = Query(None),
    departamento: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(Turma)
    if disciplina_id:
        query = query.filter(Turma.disciplina_id == disciplina_id)
    if semestre:
        query = query.filter(Turma.semestre == semestre)
    if estado:
        query = query.filter(Turma.estado == estado)
    if departamento:
        query = query.join(Disciplina).filter(Disciplina.departamento == departamento)

    turmas = query.all()
    return [TurmaService.enriquecer_turma(db, t) for t in turmas]

@router.get("/{id}", response_model=TurmaResponse)
def obter_turma(id: int, db: Session = Depends(get_db)):
    turma = db.query(Turma).filter(Turma.id == id).first()
    if not turma:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Turma com ID {id} não encontrada")
    return TurmaService.enriquecer_turma(db, turma)

@router.put("/{id}", response_model=TurmaResponse)
def atualizar_turma(id: int, payload: TurmaUpdate, db: Session = Depends(get_db)):
    turma = db.query(Turma).filter(Turma.id == id).first()
    if not turma:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Turma com ID {id} não encontrada")

    update_data = payload.model_dump(exclude_unset=True)
    if "disciplina_id" in update_data:
        disciplina = db.query(Disciplina).filter(Disciplina.id == update_data["disciplina_id"]).first()
        if not disciplina:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disciplina informada não encontrada")

    for k, v in update_data.items():
        setattr(turma, k, v)

    db.commit()
    db.refresh(turma)
    return TurmaService.enriquecer_turma(db, turma)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_turma(id: int, db: Session = Depends(get_db)):
    turma = db.query(Turma).filter(Turma.id == id).first()
    if not turma:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Turma com ID {id} não encontrada")
    db.delete(turma)
    db.commit()
    return None

@router.get("/{id}/fila", response_model=FilaEsperaResponse)
def consultar_fila_espera(id: int, db: Session = Depends(get_db)):
    return MatriculaService.consultar_fila_turma(db, id)

@router.get("/{id}/lista-espera", response_model=FilaEsperaResponse)
def consultar_lista_espera(id: int, db: Session = Depends(get_db)):
    return MatriculaService.consultar_fila_turma(db, id)

@router.post("/{id}/finalizar-periodo-matricula", response_model=TurmaResponse)
def finalizar_periodo_matricula_por_turma(id: int, db: Session = Depends(get_db)):
    """
    Regra 5: Turma com menos de 5 matrículas confirmadas ao fim do período de matrícula
    é cancelada, e todas as suas matrículas passam ao estado cancelada.
    """
    turma = TurmaService.finalizar_periodo_matricula_turma(db, id)
    return turma

@router.post("/finalizar-periodo-matricula", response_model=List[TurmaResponse])
def finalizar_periodo_matricula_por_semestre(semestre: str = Query(...), db: Session = Depends(get_db)):
    """
    Regra 5: Executa a validação de mínimo de 5 matrículas confirmadas para todas as turmas do semestre.
    """
    return TurmaService.finalizar_periodo_matricula_semestre(db, semestre)
