from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.turma import Turma
from app.models.matricula import Matricula
from app.models.enums import EstadoTurma, EstadoMatricula

class TurmaService:

    @staticmethod
    def enriquecer_turma(db: Session, turma: Turma) -> Turma:
        """
        Adiciona atributos calculados 'vagas_ocupadas' e 'vagas_disponiveis' para a resposta da API.
        """
        confirmadas = db.query(Matricula).filter(
            Matricula.turma_id == turma.id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        ).count()
        setattr(turma, "vagas_ocupadas", confirmadas)
        setattr(turma, "vagas_disponiveis", max(0, turma.numero_vagas - confirmadas))
        return turma

    @staticmethod
    def finalizar_periodo_matricula_turma(db: Session, turma_id: int) -> Turma:
        """
        Regra 5: Turma com menos de 5 matrículas confirmadas ao fim do período de matrícula é cancelada,
        e todas as suas matrículas passam ao estado cancelada.
        """
        turma = db.query(Turma).filter(Turma.id == turma_id).first()
        if not turma:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Turma {turma_id} não encontrada")

        if turma.estado == EstadoTurma.CANCELADA:
            return TurmaService.enriquecer_turma(db, turma)

        confirmadas = db.query(Matricula).filter(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        ).count()

        if confirmadas < 5:
            turma.estado = EstadoTurma.CANCELADA
            # Cancela todas as matrículas da turma
            todas_matriculas = db.query(Matricula).filter(Matricula.turma_id == turma_id).all()
            for mat in todas_matriculas:
                mat.estado = EstadoMatricula.CANCELADA
            db.commit()
            db.refresh(turma)

        return TurmaService.enriquecer_turma(db, turma)

    @staticmethod
    def finalizar_periodo_matricula_semestre(db: Session, semestre: str) -> List[Turma]:
        """
        Aplica a Regra 5 para todas as turmas de um determinado semestre.
        """
        turmas = db.query(Turma).filter(Turma.semestre == semestre).all()
        atualizadas = []
        for turma in turmas:
            atualizada = TurmaService.finalizar_periodo_matricula_turma(db, turma.id)
            atualizadas.append(atualizada)
        return atualizadas
