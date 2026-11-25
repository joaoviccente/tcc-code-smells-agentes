from sqlalchemy import Column, Integer, String, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoTurma

class Turma(Base):
    __tablename__ = "turmas"

    id = Column(Integer, primary_key=True, index=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False, index=True)
    semestre = Column(String(20), nullable=False, index=True)
    professor = Column(String(150), nullable=False)
    numero_vagas = Column(Integer, nullable=False)
    horario = Column(String(100), nullable=False)
    estado = Column(SQLEnum(EstadoTurma, values_callable=lambda obj: [e.value for e in obj]), default=EstadoTurma.ABERTA, nullable=False)

    disciplina = relationship("Disciplina", back_populates="turmas")
    matriculas = relationship("Matricula", back_populates="turma", cascade="all, delete-orphan")
