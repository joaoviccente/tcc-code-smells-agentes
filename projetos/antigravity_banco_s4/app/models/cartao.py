from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, Enum as SQLEnum, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoCartao


class Cartao(Base):
    __tablename__ = "cartoes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conta_id = Column(Integer, ForeignKey("contas.id"), nullable=False, index=True)
    numero = Column(String(20), unique=True, index=True, nullable=False)
    limite = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    estado = Column(SQLEnum(EstadoCartao), default=EstadoCartao.ATIVO, nullable=False)
    data_criacao = Column(DateTime, default=datetime.utcnow, nullable=False)

    conta = relationship("Conta", back_populates="cartoes")
    faturas = relationship("Fatura", back_populates="cartao", cascade="all, delete-orphan")
