from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, Enum as SQLEnum, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoTarifa


class Tarifa(Base):
    __tablename__ = "tarifas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conta_id = Column(Integer, ForeignKey("contas.id"), nullable=False, index=True)
    tipo = Column(String(100), nullable=False)
    valor = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    data = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    estado = Column(SQLEnum(EstadoTarifa), default=EstadoTarifa.COBRADA, nullable=False)

    conta = relationship("Conta", back_populates="tarifas")
