from sqlalchemy import Column, DateTime, Enum, Integer, String
from sqlalchemy.orm import relationship

from app.config import CategoriaUsuario, SituacaoUsuario
from app.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nome = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    matricula = Column(String(50), unique=True, index=True, nullable=False)
    categoria = Column(Enum(CategoriaUsuario), nullable=False)
    situacao = Column(Enum(SituacaoUsuario), default=SituacaoUsuario.ATIVO, nullable=False)
    suspenso_ate = Column(DateTime, nullable=True)

    emprestimos = relationship("Emprestimo", back_populates="usuario")
    reservas = relationship("Reserva", back_populates="usuario")
