from decimal import Decimal
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import EstadoCartao
from app.utils import utc_now


class Cartao(Base):
    __tablename__ = "cartoes"

    id = Column(Integer, primary_key=True, index=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False)
    numero = Column(String(20), unique=True, index=True, nullable=False)
    limite = Column(Numeric(14, 2), default=Decimal("1000.00"), nullable=False)
    estado = Column(SQLEnum(EstadoCartao), default=EstadoCartao.ATIVO, nullable=False)
    data_criacao = Column(DateTime, default=utc_now, nullable=False)

    conta = relationship("Conta", back_populates="cartoes")
    faturas = relationship("Fatura", back_populates="cartao", cascade="all, delete-orphan")
