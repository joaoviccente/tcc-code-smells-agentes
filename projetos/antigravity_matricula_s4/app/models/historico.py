from sqlalchemy import Column, Integer, String, Float, ForeignKey, Enum as SqlEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import SituacaoHistorico


class Historico(Base):
    __tablename__ = "historicos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id", ondelete="CASCADE"), nullable=False, index=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False, index=True)
    semestre = Column(String(20), nullable=False)
    nota = Column(Float, nullable=True)
    situacao = Column(SqlEnum(SituacaoHistorico), nullable=False)

    aluno = relationship("Aluno", back_populates="historicos")
    disciplina = relationship("Disciplina", back_populates="historicos")
