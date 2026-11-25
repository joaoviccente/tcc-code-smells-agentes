from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric
from sqlalchemy.orm import relationship

from app.config import EstadoMulta
from app.database import Base


class Multa(Base):
    __tablename__ = "multas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    emprestimo_id = Column(Integer, ForeignKey("emprestimos.id", ondelete="CASCADE"), nullable=False, index=True)
    valor = Column(Numeric(10, 2), nullable=False)
    estado = Column(Enum(EstadoMulta), default=EstadoMulta.ABERTA, nullable=False)
    data_geracao = Column(DateTime, nullable=False)
    data_pagamento = Column(DateTime, nullable=True)

    emprestimo = relationship("Emprestimo", back_populates="multas")
