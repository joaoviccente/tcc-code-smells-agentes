"""Modelo de banco de dados para a entidade Turma."""

from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoTurma


class Turma(Base):
    __tablename__ = "turmas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)
    semestre = Column(String(20), nullable=False, index=True)
    professor = Column(String(150), nullable=False)
    numero_vagas = Column(Integer, nullable=False)
    horario = Column(String(100), nullable=False)
    estado = Column(SAEnum(EstadoTurma), default=EstadoTurma.ABERTA, nullable=False)

    disciplina = relationship("Disciplina", back_populates="turmas")
    matriculas = relationship("Matricula", back_populates="turma", cascade="all, delete-orphan")
