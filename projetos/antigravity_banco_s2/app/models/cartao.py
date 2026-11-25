from decimal import Decimal
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import EstadoCartao, get_current_time


class Cartao(Base):
    __tablename__ = "cartoes"

    id = Column(Integer, primary_key=True, index=True)
    conta_id = Column(Integer, ForeignKey("contas.id"), nullable=False, index=True)
    numero = Column(String(20), unique=True, index=True, nullable=False)
    limite = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    estado = Column(
        SQLEnum(EstadoCartao, values_callable=lambda x: [e.value for e in x]),
        default=EstadoCartao.ATIVO,
        nullable=False,
    )
    created_at = Column(DateTime, default=get_current_time, nullable=False)

    conta = relationship("Conta", back_populates="cartoes")
    faturas = relationship("Fatura", back_populates="cartao", cascade="all, delete-orphan")
