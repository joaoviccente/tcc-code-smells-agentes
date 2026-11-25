from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import CategoriaCliente, SituacaoCliente


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nome = Column(String(150), nullable=False)
    cpf = Column(String(14), unique=True, index=True, nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    categoria = Column(SQLEnum(CategoriaCliente), default=CategoriaCliente.COMUM, nullable=False)
    situacao = Column(SQLEnum(SituacaoCliente), default=SituacaoCliente.ATIVO, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    contas = relationship("Conta", back_populates="cliente", cascade="all, delete-orphan")
