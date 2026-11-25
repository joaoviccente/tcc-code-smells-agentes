from sqlalchemy import Column, Integer, String, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import CategoriaAluno, SituacaoAluno

class Aluno(Base):
    __tablename__ = "alunos"

    id = Column(Integer, primary_key=True, index=True)
    matricula = Column(String(50), unique=True, nullable=False, index=True)
    nome = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    categoria = Column(SQLEnum(CategoriaAluno, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    situacao = Column(SQLEnum(SituacaoAluno, values_callable=lambda obj: [e.value for e in obj]), default=SituacaoAluno.ATIVO, nullable=False)

    matriculas = relationship("Matricula", back_populates="aluno", cascade="all, delete-orphan")
    historicos = relationship("Historico", back_populates="aluno", cascade="all, delete-orphan")
