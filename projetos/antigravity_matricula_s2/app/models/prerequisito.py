"""Modelo de banco de dados para a entidade PreRequisito."""

from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class PreRequisito(Base):
    __tablename__ = "pre_requisitos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)
    prerequisito_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("disciplina_id", "prerequisito_id", name="uq_disciplina_prerequisito"),
    )

    disciplina = relationship("Disciplina", foreign_keys=[disciplina_id], back_populates="prerequisitos_exigidos")
    prerequisito = relationship("Disciplina", foreign_keys=[prerequisito_id], back_populates="exigida_como_prerequisito")
