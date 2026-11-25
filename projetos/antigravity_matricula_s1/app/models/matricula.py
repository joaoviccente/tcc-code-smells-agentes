from datetime import datetime, timezone
from sqlalchemy import Column, Integer, DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoMatricula


class Matricula(Base):
    __tablename__ = "matriculas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id", ondelete="CASCADE"), nullable=False)
    turma_id = Column(Integer, ForeignKey("turmas.id", ondelete="CASCADE"), nullable=False)
    data = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    data_limite_confirmacao = Column(DateTime, nullable=True)
    estado = Column(SAEnum(EstadoMatricula), default=EstadoMatricula.SOLICITADA, nullable=False)

    aluno = relationship("Aluno", back_populates="matriculas")
    turma = relationship("Turma", back_populates="matriculas")
