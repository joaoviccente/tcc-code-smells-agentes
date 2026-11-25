from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, Numeric, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import EstadoFatura


class Fatura(Base):
    __tablename__ = "faturas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cartao_id = Column(Integer, ForeignKey("cartoes.id"), nullable=False, index=True)
    mes_referencia = Column(String(7), nullable=False)  # ex: "2026-11"
    valor = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    data_vencimento = Column(Date, nullable=False, index=True)
    estado = Column(SQLEnum(EstadoFatura), default=EstadoFatura.ABERTA, nullable=False)
    valor_pago = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    data_pagamento = Column(DateTime, nullable=True)
    juros_acumulados = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)

    cartao = relationship("Cartao", back_populates="faturas")
