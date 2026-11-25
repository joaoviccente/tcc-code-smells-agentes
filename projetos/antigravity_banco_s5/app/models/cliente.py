from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import CategoriaCliente, SituacaoCliente
from app.utils import utc_now


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(120), nullable=False)
    cpf = Column(String(14), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    categoria = Column(SQLEnum(CategoriaCliente), default=CategoriaCliente.COMUM, nullable=False)
    situacao = Column(SQLEnum(SituacaoCliente), default=SituacaoCliente.ATIVO, nullable=False)
    data_criacao = Column(DateTime, default=utc_now, nullable=False)

    contas = relationship("Conta", back_populates="cliente", cascade="all, delete-orphan")

