from decimal import Decimal
import enum
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class EstadoCartao(str, enum.Enum):
    ATIVO = "ativo"
    BLOQUEADO = "bloqueado"
    CANCELADO = "cancelado"


class Cartao(Base):
    __tablename__ = "cartoes"

    id = Column(Integer, primary_key=True, index=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False, index=True)
    numero = Column(String(30), unique=True, nullable=False, index=True)
    limite = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    estado = Column(
        Enum(EstadoCartao, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=EstadoCartao.ATIVO,
    )
    data_criacao = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    conta = relationship("Conta", back_populates="cartoes")
    faturas = relationship("Fatura", back_populates="cartao", cascade="all, delete-orphan")
