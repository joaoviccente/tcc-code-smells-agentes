from sqlalchemy import Column, Integer, String, Float, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import SituacaoHistorico


class Historico(Base):
    __tablename__ = "historicos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id", ondelete="CASCADE"), nullable=False)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)
    semestre = Column(String(20), nullable=False, index=True)
    nota = Column(Float, nullable=True)
    situacao = Column(SAEnum(SituacaoHistorico), nullable=False)

    aluno = relationship("Aluno", back_populates="historico")
    disciplina = relationship("Disciplina", back_populates="historico")
