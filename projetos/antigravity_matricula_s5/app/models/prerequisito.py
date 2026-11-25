from sqlalchemy import Column, Integer, ForeignKey
from app.database import Base

class PreRequisito(Base):
    __tablename__ = "prerequisitos"

    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), primary_key=True)
    prerequisito_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), primary_key=True)

    def __repr__(self):
        return f"<PreRequisito(disciplina_id={self.disciplina_id}, prerequisito_id={self.prerequisito_id})>"
