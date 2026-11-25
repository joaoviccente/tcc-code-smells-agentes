"""Modelo de banco de dados para a entidade Aluno."""

from sqlalchemy import Column, Integer, String, Enum as SAEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import CategoriaAluno, SituacaoAluno


class Aluno(Base):
    __tablename__ = "alunos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nome = Column(String(150), nullable=False)
    matricula = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    categoria = Column(SAEnum(CategoriaAluno), nullable=False)
    situacao = Column(SAEnum(SituacaoAluno), default=SituacaoAluno.ATIVO, nullable=False)

    matriculas = relationship("Matricula", back_populates="aluno", cascade="all, delete-orphan")
    historico = relationship("Historico", back_populates="aluno", cascade="all, delete-orphan")
