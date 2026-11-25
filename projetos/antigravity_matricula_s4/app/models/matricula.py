from datetime import datetime, timezone
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Enum as SqlEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import EstadoMatricula


def utc_now():
    return datetime.now(timezone.utc)


class Matricula(Base):
    __tablename__ = "matriculas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id", ondelete="CASCADE"), nullable=False)
    turma_id = Column(Integer, ForeignKey("turmas.id", ondelete="CASCADE"), nullable=False)
    data = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    estado = Column(SqlEnum(EstadoMatricula), nullable=False, default=EstadoMatricula.SOLICITADA)
    
    # Campo para registrar quando o aluno da lista de espera foi contemplado com vaga liberada
    # Ele tem 48 horas a partir desse timestamp para confirmar
    data_oferta_vaga = Column(DateTime(timezone=True), nullable=True)

    aluno = relationship("Aluno", back_populates="matriculas")
    turma = relationship("Turma", back_populates="matriculas")
