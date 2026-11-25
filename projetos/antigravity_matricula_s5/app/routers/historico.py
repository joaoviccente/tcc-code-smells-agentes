from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.historico import Historico
from app.models.aluno import Aluno
from app.models.disciplina import Disciplina
from app.models.enums import SituacaoHistorico
from app.schemas.historico import HistoricoCreate, HistoricoResponse

router = APIRouter(prefix="/historico", tags=["Histórico"])


@router.post("", response_model=HistoricoResponse, status_code=status.HTTP_201_CREATED)
def registrar_historico(payload: HistoricoCreate, db: Session = Depends(get_db)):
    """
    Registra um resultado acadêmico no histórico do aluno.
    Útil para configurar aprovação em pré-requisitos e registros prévios.
    """
    aluno = db.query(Aluno).filter(Aluno.id == payload.aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {payload.aluno_id} não encontrado."
        )

    disciplina = db.query(Disciplina).filter(Disciplina.id == payload.disciplina_id).first()
    if not disciplina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina com ID {payload.disciplina_id} não encontrada."
        )

    novo_historico = Historico(
        aluno_id=payload.aluno_id,
        disciplina_id=payload.disciplina_id,
        semestre=payload.semestre,
        nota=payload.nota,
        situacao=payload.situacao
    )
    db.add(novo_historico)
    db.commit()
    db.refresh(novo_historico)
    return novo_historico


@router.get("/aluno/{aluno_id}", response_model=List[HistoricoResponse])
def consultar_historico_por_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """
    Consulta o histórico acadêmico completo de um aluno.
    """
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {aluno_id} não encontrado."
        )

    return db.query(Historico).filter(Historico.aluno_id == aluno_id).all()


@router.get("", response_model=List[HistoricoResponse])
def listar_historicos(
    aluno_id: Optional[int] = None,
    disciplina_id: Optional[int] = None,
    situacao: Optional[SituacaoHistorico] = None,
    db: Session = Depends(get_db)
):
    """Lista registros de histórico com filtros opcionais."""
    query = db.query(Historico)
    if aluno_id:
        query = query.filter(Historico.aluno_id == aluno_id)
    if disciplina_id:
        query = query.filter(Historico.disciplina_id == disciplina_id)
    if situacao:
        query = query.filter(Historico.situacao == situacao)
    return query.all()


@router.get("/{historico_id}", response_model=HistoricoResponse)
def obter_historico(historico_id: int, db: Session = Depends(get_db)):
    """Obtém um registro de histórico por ID."""
    hist = db.query(Historico).filter(Historico.id == historico_id).first()
    if not hist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registro de histórico com ID {historico_id} não encontrado."
        )
    return hist


@router.delete("/{historico_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_historico(historico_id: int, db: Session = Depends(get_db)):
    """Remove um registro de histórico."""
    hist = db.query(Historico).filter(Historico.id == historico_id).first()
    if not hist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registro de histórico com ID {historico_id} não encontrado."
        )
    db.delete(hist)
    db.commit()
    return None
