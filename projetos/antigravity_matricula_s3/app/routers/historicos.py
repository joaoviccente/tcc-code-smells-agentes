from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.historico import Historico
from app.models.aluno import Aluno
from app.models.disciplina import Disciplina
from app.models.enums import SituacaoHistorico
from app.schemas.historico import HistoricoCreate, HistoricoResponse

router = APIRouter(prefix="/historico", tags=["Histórico"])

@router.post("", response_model=HistoricoResponse, status_code=status.HTTP_201_CREATED)
def criar_registro_historico(payload: HistoricoCreate, db: Session = Depends(get_db)):
    aluno = db.query(Aluno).filter(Aluno.id == payload.aluno_id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aluno {payload.aluno_id} não encontrado")

    disciplina = db.query(Disciplina).filter(Disciplina.id == payload.disciplina_id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Disciplina {payload.disciplina_id} não encontrada")

    hist = Historico(**payload.model_dump())
    db.add(hist)
    db.commit()
    db.refresh(hist)

    return HistoricoResponse(
        id=hist.id,
        aluno_id=hist.aluno_id,
        disciplina_id=hist.disciplina_id,
        semestre=hist.semestre,
        nota=hist.nota,
        situacao=hist.situacao,
        observacao=hist.observacao,
        disciplina_codigo=disciplina.codigo,
        disciplina_nome=disciplina.nome
    )

@router.get("", response_model=List[HistoricoResponse])
def listar_historicos(
    aluno_id: Optional[int] = Query(None),
    disciplina_id: Optional[int] = Query(None),
    situacao: Optional[SituacaoHistorico] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(Historico)
    if aluno_id:
        query = query.filter(Historico.aluno_id == aluno_id)
    if disciplina_id:
        query = query.filter(Historico.disciplina_id == disciplina_id)
    if situacao:
        query = query.filter(Historico.situacao == situacao)

    registros = query.all()
    resultado = []
    for h in registros:
        resultado.append(
            HistoricoResponse(
                id=h.id,
                aluno_id=h.aluno_id,
                disciplina_id=h.disciplina_id,
                semestre=h.semestre,
                nota=h.nota,
                situacao=h.situacao,
                observacao=h.observacao,
                disciplina_codigo=h.disciplina.codigo if h.disciplina else None,
                disciplina_nome=h.disciplina.nome if h.disciplina else None
            )
        )
    return resultado

@router.get("/{id}", response_model=HistoricoResponse)
def obter_historico(id: int, db: Session = Depends(get_db)):
    h = db.query(Historico).filter(Historico.id == id).first()
    if not h:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Registro de histórico {id} não encontrado")
    return HistoricoResponse(
        id=h.id,
        aluno_id=h.aluno_id,
        disciplina_id=h.disciplina_id,
        semestre=h.semestre,
        nota=h.nota,
        situacao=h.situacao,
        observacao=h.observacao,
        disciplina_codigo=h.disciplina.codigo if h.disciplina else None,
        disciplina_nome=h.disciplina.nome if h.disciplina else None
    )

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_historico(id: int, db: Session = Depends(get_db)):
    h = db.query(Historico).filter(Historico.id == id).first()
    if not h:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Registro de histórico {id} não encontrado")
    db.delete(h)
    db.commit()
    return None
