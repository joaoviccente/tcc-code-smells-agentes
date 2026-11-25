from datetime import datetime, timezone
from sqlalchemy import Column, Integer, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoMatricula

def get_utc_now():
    return datetime.now(timezone.utc)

class Matricula(Base):
    __tablename__ = "matriculas"

    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id", ondelete="CASCADE"), nullable=False, index=True)
    turma_id = Column(Integer, ForeignKey("turmas.id", ondelete="CASCADE"), nullable=False, index=True)
    data = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    estado = Column(SQLEnum(EstadoMatricula, values_callable=lambda obj: [e.value for e in obj]), default=EstadoMatricula.SOLICITADA, nullable=False)
    data_limite_confirmacao = Column(DateTime(timezone=True), nullable=True)

    aluno = relationship("Aluno", back_populates="matriculas")
    turma = relationship("Turma", back_populates="matriculas")
