"""Rotas REST para gerenciamento do Histórico Escolar dos alunos."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.historico import Historico
from app.models.aluno import Aluno
from app.models.disciplina import Disciplina
from app.schemas.historico import HistoricoCreate, HistoricoUpdate, HistoricoResponse

router = APIRouter(prefix="/historico", tags=["Histórico"])


def formatar_historico_response(h: Historico) -> HistoricoResponse:
    return HistoricoResponse(
        id=h.id,
        aluno_id=h.aluno_id,
        disciplina_id=h.disciplina_id,
        semestre=h.semestre,
        nota=h.nota,
        situacao=h.situacao,
        disciplina_codigo=h.disciplina.codigo if h.disciplina else None,
        disciplina_nome=h.disciplina.nome if h.disciplina else None,
        aluno_nome=h.aluno.nome if h.aluno else None,
    )


@router.post("", response_model=HistoricoResponse, status_code=status.HTTP_201_CREATED)
def cadastrar_registro_historico(payload: HistoricoCreate, db: Session = Depends(get_db)):
    """Insere um novo registro de disciplina cursada no histórico."""
    aluno = db.query(Aluno).filter(Aluno.id == payload.aluno_id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado")

    disciplina = db.query(Disciplina).filter(Disciplina.id == payload.disciplina_id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disciplina não encontrada")

    novo_reg = Historico(
        aluno_id=payload.aluno_id,
        disciplina_id=payload.disciplina_id,
        semestre=payload.semestre.strip(),
        nota=payload.nota,
        situacao=payload.situacao,
    )
    db.add(novo_reg)
    db.commit()
    db.refresh(novo_reg)
    return formatar_historico_response(novo_reg)


@router.get("/aluno/{aluno_id}", response_model=List[HistoricoResponse])
def consultar_historico_por_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """Consulta o histórico acadêmico completo de um aluno."""
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado")

    registros = db.query(Historico).filter(Historico.aluno_id == aluno_id).order_by(Historico.semestre).all()
    return [formatar_historico_response(r) for r in registros]


@router.get("", response_model=List[HistoricoResponse])
def listar_historicos(
    aluno_id: Optional[int] = None,
    disciplina_id: Optional[int] = None,
    semestre: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Lista registros de histórico com filtros opcionais."""
    query = db.query(Historico)
    if aluno_id:
        query = query.filter(Historico.aluno_id == aluno_id)
    if disciplina_id:
        query = query.filter(Historico.disciplina_id == disciplina_id)
    if semestre:
        query = query.filter(Historico.semestre == semestre.strip())

    registros = query.all()
    return [formatar_historico_response(r) for r in registros]


@router.get("/{id}", response_model=HistoricoResponse)
def obter_registro_historico(id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de um registro específico de histórico."""
    reg = db.query(Historico).filter(Historico.id == id).first()
    if not reg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro de histórico não encontrado")
    return formatar_historico_response(reg)


@router.put("/{id}", response_model=HistoricoResponse)
def atualizar_registro_historico(id: int, payload: HistoricoUpdate, db: Session = Depends(get_db)):
    """Atualiza nota ou situação de um registro de histórico."""
    reg = db.query(Historico).filter(Historico.id == id).first()
    if not reg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro de histórico não encontrado")

    if payload.semestre is not None:
        reg.semestre = payload.semestre.strip()
    if payload.nota is not None:
        reg.nota = payload.nota
    if payload.situacao is not None:
        reg.situacao = payload.situacao

    db.commit()
    db.refresh(reg)
    return formatar_historico_response(reg)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_registro_historico(id: int, db: Session = Depends(get_db)):
    """Remove um registro do histórico escolar."""
    reg = db.query(Historico).filter(Historico.id == id).first()
    if not reg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro de histórico não encontrado")
    db.delete(reg)
    db.commit()
    return None
