from datetime import date
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, Numeric, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import EstadoFatura, get_current_time


class Fatura(Base):
    __tablename__ = "faturas"

    id = Column(Integer, primary_key=True, index=True)
    cartao_id = Column(Integer, ForeignKey("cartoes.id"), nullable=False, index=True)
    mes_referencia = Column(String(7), nullable=False)  # Ex: "2026-11"
    valor = Column(Numeric(14, 2), nullable=False)
    valor_original = Column(Numeric(14, 2), nullable=False)
    data_vencimento = Column(Date, nullable=False)
    data_pagamento = Column(DateTime, nullable=True)
    estado = Column(
        SQLEnum(EstadoFatura, values_callable=lambda x: [e.value for e in x]),
        default=EstadoFatura.ABERTA,
        nullable=False,
    )
    dias_atraso = Column(Integer, default=0, nullable=False)
    juros_acumulados = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    created_at = Column(DateTime, default=get_current_time, nullable=False)

    cartao = relationship("Cartao", back_populates="faturas")
