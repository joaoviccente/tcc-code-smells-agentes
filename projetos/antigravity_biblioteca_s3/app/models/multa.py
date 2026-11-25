from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, Numeric, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoMulta
from app.utils import get_utcnow


class Multa(Base):
    __tablename__ = "multas"

    id = Column(Integer, primary_key=True, index=True)
    emprestimo_id = Column(Integer, ForeignKey("emprestimos.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    valor = Column(Numeric(10, 2), nullable=False)
    estado = Column(SQLEnum(EstadoMulta), nullable=False, default=EstadoMulta.ABERTA)
    data_geracao = Column(DateTime, nullable=False, default=get_utcnow)
    data_pagamento = Column(DateTime, nullable=True)

    emprestimo = relationship("Emprestimo", back_populates="multa")
