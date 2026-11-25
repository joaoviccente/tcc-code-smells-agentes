from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.aluno import Aluno
from app.models.enums import CategoriaAluno, SituacaoAluno
from app.schemas.aluno import AlunoCreate, AlunoUpdate, AlunoResponse
from app.schemas.matricula import MatriculaResponse
from app.schemas.historico import HistoricoResponse
from app.models.matricula import Matricula
from app.models.historico import Historico

router = APIRouter(prefix="/alunos", tags=["Alunos"])


@router.post("", response_model=AlunoResponse, status_code=status.HTTP_201_CREATED)
def criar_aluno(payload: AlunoCreate, db: Session = Depends(get_db)):
    """Cria um novo aluno no sistema."""
    # Verificar unicidade de matrícula e e-mail
    if db.query(Aluno).filter(Aluno.matricula == payload.matricula).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe aluno cadastrado com a matrícula '{payload.matricula}'."
        )
    if db.query(Aluno).filter(Aluno.e_mail == payload.e_mail).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe aluno cadastrado com o e-mail '{payload.e_mail}'."
        )

    novo_aluno = Aluno(
        nome=payload.nome,
        matricula=payload.matricula,
        e_mail=payload.e_mail,
        categoria=payload.categoria,
        situacao=payload.situacao,
    )
    db.add(novo_aluno)
    db.commit()
    db.refresh(novo_aluno)
    return novo_aluno


@router.get("", response_model=List[AlunoResponse])
def listar_alunos(
    categoria: Optional[CategoriaAluno] = None,
    situacao: Optional[SituacaoAluno] = None,
    db: Session = Depends(get_db)
):
    """Lista todos os alunos, com filtros opcionais por categoria e situação."""
    query = db.query(Aluno)
    if categoria:
        query = query.filter(Aluno.categoria == categoria)
    if situacao:
        query = query.filter(Aluno.situacao == situacao)
    return query.all()


@router.get("/{aluno_id}", response_model=AlunoResponse)
def obter_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """Obtém os detalhes de um aluno por ID."""
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {aluno_id} não encontrado."
        )
    return aluno


@router.put("/{aluno_id}", response_model=AlunoResponse)
def atualizar_aluno(aluno_id: int, payload: AlunoUpdate, db: Session = Depends(get_db)):
    """Atualiza os dados de um aluno."""
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {aluno_id} não encontrado."
        )

    update_data = payload.model_dump(exclude_unset=True)
    if "e_mail" in update_data:
        email_existente = (
            db.query(Aluno)
            .filter(Aluno.e_mail == update_data["e_mail"], Aluno.id != aluno_id)
            .first()
        )
        if email_existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"E-mail '{update_data['e_mail']}' já está em uso por outro aluno."
            )

    for field, value in update_data.items():
        setattr(aluno, field, value)

    db.commit()
    db.refresh(aluno)
    return aluno


@router.delete("/{aluno_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """Remove um aluno do sistema."""
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {aluno_id} não encontrado."
        )
    db.delete(aluno)
    db.commit()
    return None


@router.get("/{aluno_id}/matriculas", response_model=List[MatriculaResponse])
def listar_matriculas_do_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """Retorna todas as matrículas de um aluno."""
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {aluno_id} não encontrado."
        )
    return db.query(Matricula).filter(Matricula.aluno_id == aluno_id).all()


@router.get("/{aluno_id}/historico", response_model=List[HistoricoResponse])
def listar_historico_do_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """Retorna o histórico acadêmico completo do aluno."""
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {aluno_id} não encontrado."
        )
    return db.query(Historico).filter(Historico.aluno_id == aluno_id).all()
