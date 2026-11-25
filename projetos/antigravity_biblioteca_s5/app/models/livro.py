from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Livro(Base):
    __tablename__ = "livros"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    titulo = Column(String(255), nullable=False, index=True)
    autor = Column(String(255), nullable=False, index=True)
    isbn = Column(String(20), unique=True, index=True, nullable=False)
    ano = Column(Integer, nullable=False)
    area_conhecimento = Column(String(100), nullable=False, index=True)

    exemplares = relationship("Exemplar", back_populates="livro", cascade="all, delete-orphan")
    reservas = relationship("Reserva", back_populates="livro", cascade="all, delete-orphan")
