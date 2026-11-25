from sqlalchemy import Column, Integer, String, Float, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import SituacaoHistorico

class Historico(Base):
    __tablename__ = "historicos"

    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id", ondelete="CASCADE"), nullable=False, index=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False, index=True)
    semestre = Column(String(20), nullable=False, index=True)
    nota = Column(Float, nullable=True)
    situacao = Column(SQLEnum(SituacaoHistorico, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    observacao = Column(String(255), nullable=True)

    aluno = relationship("Aluno", back_populates="historicos")
    disciplina = relationship("Disciplina", back_populates="historicos")
