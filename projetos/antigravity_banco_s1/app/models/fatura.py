from decimal import Decimal
import enum
from datetime import date, datetime, timezone
from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class EstadoFatura(str, enum.Enum):
    ABERTA = "aberta"
    FECHADA = "fechada"
    PAGA = "paga"
    ATRASADA = "atrasada"


class Fatura(Base):
    __tablename__ = "faturas"

    id = Column(Integer, primary_key=True, index=True)
    cartao_id = Column(Integer, ForeignKey("cartoes.id", ondelete="CASCADE"), nullable=False, index=True)
    mes_referencia = Column(String(7), nullable=False)  # Formato YYYY-MM
    valor = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    valor_pago = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    juros_acumulados = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    data_vencimento = Column(Date, nullable=False)
    data_pagamento = Column(DateTime, nullable=True)
    estado = Column(
        Enum(EstadoFatura, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=EstadoFatura.ABERTA,
    )
    data_criacao = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    cartao = relationship("Cartao", back_populates="faturas")
