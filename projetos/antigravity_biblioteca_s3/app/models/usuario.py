from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import CategoriaUsuario, SituacaoUsuario


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    matricula = Column(String(100), unique=True, index=True, nullable=False)
    categoria = Column(SQLEnum(CategoriaUsuario), nullable=False)
    situacao = Column(SQLEnum(SituacaoUsuario), nullable=False, default=SituacaoUsuario.ATIVO)
    data_suspensao_fim = Column(DateTime, nullable=True)

    emprestimos = relationship("Emprestimo", back_populates="usuario", cascade="all, delete-orphan")
    reservas = relationship("Reserva", back_populates="usuario", cascade="all, delete-orphan")
