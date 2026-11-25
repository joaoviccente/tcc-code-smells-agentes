from sqlalchemy import Column, Integer, String, Enum as SqlEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import CategoriaAluno, SituacaoAluno


class Aluno(Base):
    __tablename__ = "alunos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nome = Column(String(150), nullable=False)
    matricula = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(150), unique=True, nullable=False, index=True)
    categoria = Column(SqlEnum(CategoriaAluno), nullable=False)
    situacao = Column(SqlEnum(SituacaoAluno), nullable=False, default=SituacaoAluno.ATIVO)

    matriculas = relationship("Matricula", back_populates="aluno", cascade="all, delete-orphan")
    historicos = relationship("Historico", back_populates="aluno", cascade="all, delete-orphan")
