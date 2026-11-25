from sqlalchemy import Column, Integer, String, ForeignKey, Enum as SqlEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import EstadoTurma


class Turma(Base):
    __tablename__ = "turmas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)
    semestre = Column(String(20), nullable=False, index=True)
    professor = Column(String(150), nullable=False)
    numero_vagas = Column(Integer, nullable=False)
    horario = Column(String(100), nullable=False)
    estado = Column(SqlEnum(EstadoTurma), nullable=False, default=EstadoTurma.ABERTA)

    disciplina = relationship("Disciplina", back_populates="turmas")
    matriculas = relationship("Matricula", back_populates="turma", cascade="all, delete-orphan")
