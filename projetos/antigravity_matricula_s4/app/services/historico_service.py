from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.historico import Historico
from app.models.aluno import Aluno
from app.models.disciplina import Disciplina
from app.config import SituacaoHistorico
from app.schemas.historico import HistoricoCreate


def get_historico_by_aluno(db: Session, aluno_id: int) -> List[Historico]:
    # Verificar se aluno existe
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {aluno_id} não encontrado."
        )
    return db.query(Historico).filter(Historico.aluno_id == aluno_id).all()


def create_historico(db: Session, data: HistoricoCreate) -> Historico:
    aluno = db.query(Aluno).filter(Aluno.id == data.aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {data.aluno_id} não encontrado."
        )

    disciplina = db.query(Disciplina).filter(Disciplina.id == data.disciplina_id).first()
    if not disciplina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina com ID {data.disciplina_id} não encontrada."
        )

    historico = Historico(
        aluno_id=data.aluno_id,
        disciplina_id=data.disciplina_id,
        semestre=data.semestre,
        nota=data.nota,
        situacao=data.situacao,
    )
    db.add(historico)
    db.commit()
    db.refresh(historico)
    return historico


def count_reprovacoes_disciplina(db: Session, aluno_id: int, disciplina_id: int) -> int:
    """
    Regra 3: Conta reprovações do aluno na disciplina (reprovado ou reprovado_por_falta).
    """
    return db.query(Historico).filter(
        Historico.aluno_id == aluno_id,
        Historico.disciplina_id == disciplina_id,
        Historico.situacao.in_([SituacaoHistorico.REPROVADO, SituacaoHistorico.REPROVADO_POR_FALTA])
    ).count()


def is_aprovado_na_disciplina(db: Session, aluno_id: int, disciplina_id: int) -> bool:
    """
    Regra 1: Verifica se o aluno foi aprovado na disciplina.
    """
    return db.query(Historico).filter(
        Historico.aluno_id == aluno_id,
        Historico.disciplina_id == disciplina_id,
        Historico.situacao == SituacaoHistorico.APROVADO
    ).first() is not None


def count_trancamentos_disciplina(db: Session, aluno_id: int, disciplina_id: int) -> int:
    """
    Regra 4: Conta trancamentos anteriores do aluno na mesma disciplina.
    """
    return db.query(Historico).filter(
        Historico.aluno_id == aluno_id,
        Historico.disciplina_id == disciplina_id,
        Historico.situacao == SituacaoHistorico.TRANCADO
    ).count()


def count_trancamentos_semestre(db: Session, aluno_id: int, semestre: str) -> int:
    """
    Regra 7: Conta trancamentos do aluno em um mesmo semestre.
    """
    return db.query(Historico).filter(
        Historico.aluno_id == aluno_id,
        Historico.semestre == semestre,
        Historico.situacao == SituacaoHistorico.TRANCADO
    ).count()
