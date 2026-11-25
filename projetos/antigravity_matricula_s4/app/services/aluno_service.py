from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.aluno import Aluno
from app.schemas.aluno import AlunoCreate, AlunoUpdate


def get_aluno_by_id(db: Session, aluno_id: int) -> Aluno:
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {aluno_id} não encontrado."
        )
    return aluno


def get_aluno_by_matricula(db: Session, matricula: str) -> Optional[Aluno]:
    return db.query(Aluno).filter(Aluno.matricula == matricula).first()


def get_aluno_by_email(db: Session, email: str) -> Optional[Aluno]:
    return db.query(Aluno).filter(Aluno.email == email).first()


def list_alunos(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    categoria: Optional[str] = None,
    situacao: Optional[str] = None
) -> List[Aluno]:
    query = db.query(Aluno)
    if categoria:
        query = query.filter(Aluno.categoria == categoria)
    if situacao:
        query = query.filter(Aluno.situacao == situacao)
    return query.offset(skip).limit(limit).all()


def create_aluno(db: Session, data: AlunoCreate) -> Aluno:
    if get_aluno_by_matricula(db, data.matricula):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe aluno cadastrado com a matrícula '{data.matricula}'."
        )
    if get_aluno_by_email(db, data.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe aluno cadastrado com o e-mail '{data.email}'."
        )

    aluno = Aluno(
        nome=data.nome,
        matricula=data.matricula,
        email=data.email,
        categoria=data.categoria,
        situacao=data.situacao,
    )
    db.add(aluno)
    db.commit()
    db.refresh(aluno)
    return aluno


def update_aluno(db: Session, aluno_id: int, data: AlunoUpdate) -> Aluno:
    aluno = get_aluno_by_id(db, aluno_id)

    if data.matricula and data.matricula != aluno.matricula:
        existing = get_aluno_by_matricula(db, data.matricula)
        if existing and existing.id != aluno.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe aluno cadastrado com a matrícula '{data.matricula}'."
            )
        aluno.matricula = data.matricula

    if data.email and data.email != aluno.email:
        existing = get_aluno_by_email(db, data.email)
        if existing and existing.id != aluno.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe aluno cadastrado com o e-mail '{data.email}'."
            )
        aluno.email = data.email

    if data.nome is not None:
        aluno.nome = data.nome
    if data.categoria is not None:
        aluno.categoria = data.categoria
    if data.situacao is not None:
        aluno.situacao = data.situacao

    db.commit()
    db.refresh(aluno)
    return aluno


def delete_aluno(db: Session, aluno_id: int) -> None:
    aluno = get_aluno_by_id(db, aluno_id)
    db.delete(aluno)
    db.commit()
