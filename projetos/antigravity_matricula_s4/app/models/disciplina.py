from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class Disciplina(Base):
    __tablename__ = "disciplinas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo = Column(String(20), unique=True, nullable=False, index=True)
    nome = Column(String(150), nullable=False)
    numero_creditos = Column(Integer, nullable=False)
    carga_horaria = Column(Integer, nullable=False)
    departamento = Column(String(100), nullable=False, index=True)

    turmas = relationship("Turma", back_populates="disciplina", cascade="all, delete-orphan")
    historicos = relationship("Historico", back_populates="disciplina", cascade="all, delete-orphan")
    
    # Pré-requisitos exigidos por esta disciplina
    pre_requisitos = relationship(
        "PreRequisito",
        foreign_keys="PreRequisito.disciplina_id",
        back_populates="disciplina",
        cascade="all, delete-orphan"
    )
    # Onde esta disciplina é exigida como pré-requisito
    exigida_como_pre_requisito = relationship(
        "PreRequisito",
        foreign_keys="PreRequisito.pre_requisito_id",
        back_populates="disciplina_requisito",
        cascade="all, delete-orphan"
    )


class PreRequisito(Base):
    __tablename__ = "pre_requisitos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)
    pre_requisito_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)

    disciplina = relationship("Disciplina", foreign_keys=[disciplina_id], back_populates="pre_requisitos")
    disciplina_requisito = relationship("Disciplina", foreign_keys=[pre_requisito_id], back_populates="exigida_como_pre_requisito")

    __table_args__ = (
        UniqueConstraint("disciplina_id", "pre_requisito_id", name="uq_disciplina_prerequisito"),
    )
