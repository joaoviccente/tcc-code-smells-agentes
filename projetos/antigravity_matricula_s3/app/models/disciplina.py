from sqlalchemy import Column, Integer, String, Table, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

# Association table for PreRequisito
pre_requisitos = Table(
    "pre_requisitos",
    Base.metadata,
    Column("disciplina_id", Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), primary_key=True),
    Column("pre_requisito_id", Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), primary_key=True)
)

class Disciplina(Base):
    __tablename__ = "disciplinas"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(20), unique=True, nullable=False, index=True)
    nome = Column(String(150), nullable=False)
    numero_creditos = Column(Integer, nullable=False)
    carga_horaria = Column(Integer, nullable=False)
    departamento = Column(String(100), nullable=False, index=True)

    # Relationships
    pre_requisitos = relationship(
        "Disciplina",
        secondary=pre_requisitos,
        primaryjoin=id == pre_requisitos.c.disciplina_id,
        secondaryjoin=id == pre_requisitos.c.pre_requisito_id,
        backref="requisito_de",
        lazy="selectin"
    )

    turmas = relationship("Turma", back_populates="disciplina", cascade="all, delete-orphan")
    historicos = relationship("Historico", back_populates="disciplina", cascade="all, delete-orphan")
