from sqlalchemy import Column, Integer, String, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoTurma

class Turma(Base):
    __tablename__ = "turmas"

    id = Column(Integer, primary_key=True, index=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="RESTRICT"), nullable=False, index=True)
    semestre = Column(String(20), nullable=False, index=True)
    professor = Column(String(120), nullable=False)
    numero_vagas = Column(Integer, nullable=False)
    horario = Column(String(150), nullable=False)
    estado = Column(SQLEnum(EstadoTurma), nullable=False, default=EstadoTurma.ABERTA)

    disciplina = relationship("Disciplina", back_populates="turmas")
    matriculas = relationship("Matricula", back_populates="turma", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Turma(id={self.id}, disciplina_id={self.disciplina_id}, semestre='{self.semestre}', vagas={self.numero_vagas}, estado='{self.estado}')>"
