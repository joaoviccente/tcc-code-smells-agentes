from sqlalchemy import Column, Integer, String, Enum as SQLEnum, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import CategoriaAluno, SituacaoAluno

class Aluno(Base):
    __tablename__ = "alunos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(120), nullable=False)
    matricula = Column(String(50), unique=True, index=True, nullable=False)
    e_mail = Column(String(120), unique=True, index=True, nullable=False)
    categoria = Column(SQLEnum(CategoriaAluno), nullable=False)
    situacao = Column(SQLEnum(SituacaoAluno), nullable=False, default=SituacaoAluno.ATIVO)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    matriculas = relationship("Matricula", back_populates="aluno", cascade="all, delete-orphan")
    historicos = relationship("Historico", back_populates="aluno", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Aluno(id={self.id}, matricula='{self.matricula}', nome='{self.nome}', categoria='{self.categoria}')>"
