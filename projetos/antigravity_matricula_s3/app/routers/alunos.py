from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.aluno import Aluno
from app.models.matricula import Matricula
from app.models.historico import Historico
from app.models.enums import CategoriaAluno, SituacaoAluno
from app.schemas.aluno import AlunoCreate, AlunoUpdate, AlunoResponse
from app.schemas.matricula import MatriculaResponse
from app.schemas.historico import HistoricoResponse
from app.services.turma_service import TurmaService

router = APIRouter(prefix="/alunos", tags=["Alunos"])

@router.post("", response_model=AlunoResponse, status_code=status.HTTP_201_CREATED)
def criar_aluno(payload: AlunoCreate, db: Session = Depends(get_db)):
    if db.query(Aluno).filter(Aluno.matricula == payload.matricula).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Aluno com matrícula '{payload.matricula}' já existe"
        )
    if db.query(Aluno).filter(Aluno.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Aluno com email '{payload.email}' já existe"
        )

    aluno = Aluno(**payload.model_dump())
    db.add(aluno)
    db.commit()
    db.refresh(aluno)
    return aluno

@router.get("", response_model=List[AlunoResponse])
def listar_alunos(
    categoria: Optional[CategoriaAluno] = Query(None),
    situacao: Optional[SituacaoAluno] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(Aluno)
    if categoria:
        query = query.filter(Aluno.categoria == categoria)
    if situacao:
        query = query.filter(Aluno.situacao == situacao)
    return query.all()

@router.get("/{id}", response_model=AlunoResponse)
def obter_aluno(id: int, db: Session = Depends(get_db)):
    aluno = db.query(Aluno).filter(Aluno.id == id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aluno com ID {id} não encontrado")
    return aluno

@router.put("/{id}", response_model=AlunoResponse)
def atualizar_aluno(id: int, payload: AlunoUpdate, db: Session = Depends(get_db)):
    aluno = db.query(Aluno).filter(Aluno.id == id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aluno com ID {id} não encontrado")

    update_data = payload.model_dump(exclude_unset=True)
    if "matricula" in update_data and update_data["matricula"] != aluno.matricula:
        if db.query(Aluno).filter(Aluno.matricula == update_data["matricula"]).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Matrícula já cadastrada")
    if "email" in update_data and update_data["email"] != aluno.email:
        if db.query(Aluno).filter(Aluno.email == update_data["email"]).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email já cadastrado")

    for k, v in update_data.items():
        setattr(aluno, k, v)

    db.commit()
    db.refresh(aluno)
    return aluno

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_aluno(id: int, db: Session = Depends(get_db)):
    aluno = db.query(Aluno).filter(Aluno.id == id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aluno com ID {id} não encontrado")
    db.delete(aluno)
    db.commit()
    return None

@router.get("/{id}/matriculas", response_model=List[MatriculaResponse])
def listar_matriculas_aluno(id: int, db: Session = Depends(get_db)):
    aluno = db.query(Aluno).filter(Aluno.id == id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aluno com ID {id} não encontrado")
    matriculas = db.query(Matricula).filter(Matricula.aluno_id == id).all()
    for m in matriculas:
        TurmaService.enriquecer_turma(db, m.turma)
    return matriculas

@router.get("/{id}/historico", response_model=List[HistoricoResponse])
def listar_historico_aluno(id: int, db: Session = Depends(get_db)):
    aluno = db.query(Aluno).filter(Aluno.id == id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aluno com ID {id} não encontrado")
    historicos = db.query(Historico).filter(Historico.aluno_id == id).all()
    resultado = []
    for h in historicos:
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
