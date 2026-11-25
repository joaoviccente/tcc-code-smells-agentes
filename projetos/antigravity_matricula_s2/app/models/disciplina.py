"""Modelo de banco de dados para a entidade Disciplina."""

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class Disciplina(Base):
    __tablename__ = "disciplinas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo = Column(String(20), unique=True, index=True, nullable=False)
    nome = Column(String(150), nullable=False)
    numero_creditos = Column(Integer, nullable=False)
    carga_horaria = Column(Integer, nullable=False)
    departamento = Column(String(100), nullable=False, index=True)

    turmas = relationship("Turma", back_populates="disciplina", cascade="all, delete-orphan")
    prerequisitos_exigidos = relationship(
        "PreRequisito",
        foreign_keys="PreRequisito.disciplina_id",
        back_populates="disciplina",
        cascade="all, delete-orphan",
    )
    exigida_como_prerequisito = relationship(
        "PreRequisito",
        foreign_keys="PreRequisito.prerequisito_id",
        back_populates="prerequisito",
        cascade="all, delete-orphan",
    )
    historico = relationship("Historico", back_populates="disciplina", cascade="all, delete-orphan")
