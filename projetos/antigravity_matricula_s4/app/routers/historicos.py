from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.historico import HistoricoCreate, HistoricoResponse
from app.services import historico_service

router = APIRouter(prefix="/historico", tags=["Histórico"])


@router.post("", response_model=HistoricoResponse, status_code=status.HTTP_201_CREATED)
def criar_historico(data: HistoricoCreate, db: Session = Depends(get_db)):
    h = historico_service.create_historico(db, data)
    return HistoricoResponse(
        id=h.id,
        aluno_id=h.aluno_id,
        disciplina_id=h.disciplina_id,
        disciplina_codigo=h.disciplina.codigo if h.disciplina else None,
        disciplina_nome=h.disciplina.nome if h.disciplina else None,
        semestre=h.semestre,
        nota=h.nota,
        situacao=h.situacao,
    )


@router.get("/aluno/{aluno_id}", response_model=List[HistoricoResponse])
def obter_historico_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """
    Histórico: consultar por aluno.
    """
    historicos = historico_service.get_historico_by_aluno(db, aluno_id)
    return [
        HistoricoResponse(
            id=h.id,
            aluno_id=h.aluno_id,
            disciplina_id=h.disciplina_id,
            disciplina_codigo=h.disciplina.codigo if h.disciplina else None,
            disciplina_nome=h.disciplina.nome if h.disciplina else None,
            semestre=h.semestre,
            nota=h.nota,
            situacao=h.situacao,
        )
        for h in historicos
    ]
