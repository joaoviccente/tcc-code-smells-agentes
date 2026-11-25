from sqlalchemy import Column, DateTime, Enum, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import CategoriaUsuario, SituacaoUsuario


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nome = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    matricula = Column(String(50), unique=True, index=True, nullable=False)
    categoria = Column(Enum(CategoriaUsuario), nullable=False)
    situacao = Column(Enum(SituacaoUsuario), default=SituacaoUsuario.ATIVO, nullable=False)
    data_fim_suspensao = Column(DateTime(timezone=True), nullable=True)

    emprestimos = relationship("Emprestimo", back_populates="usuario", cascade="all, delete-orphan")
    reservas = relationship("Reserva", back_populates="usuario", cascade="all, delete-orphan")
