from sqlalchemy import Column, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.config import EstadoExemplar
from app.database import Base


class Exemplar(Base):
    __tablename__ = "exemplares"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    livro_id = Column(Integer, ForeignKey("livros.id", ondelete="CASCADE"), nullable=False, index=True)
    codigo_tombo = Column(String(50), unique=True, index=True, nullable=False)
    estado = Column(Enum(EstadoExemplar), default=EstadoExemplar.DISPONIVEL, nullable=False)

    livro = relationship("Livro", back_populates="exemplares")
    emprestimos = relationship("Emprestimo", back_populates="exemplar")
