from sqlalchemy import Column, Integer, String, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoExemplar


class Exemplar(Base):
    __tablename__ = "exemplares"

    id = Column(Integer, primary_key=True, index=True)
    livro_id = Column(Integer, ForeignKey("livros.id", ondelete="CASCADE"), nullable=False, index=True)
    codigo_tombo = Column(String(100), unique=True, index=True, nullable=False)
    estado = Column(SQLEnum(EstadoExemplar), nullable=False, default=EstadoExemplar.DISPONIVEL)

    livro = relationship("Livro", back_populates="exemplares")
    emprestimos = relationship("Emprestimo", back_populates="exemplar", cascade="all, delete-orphan")
    reservas = relationship("Reserva", back_populates="exemplar")
