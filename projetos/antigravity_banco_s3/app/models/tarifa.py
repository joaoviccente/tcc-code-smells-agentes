from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, Enum as SQLEnum, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import TipoTarifa, EstadoTarifa


class Tarifa(Base):
    __tablename__ = "tarifas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conta_id = Column(Integer, ForeignKey("contas.id"), nullable=False, index=True)
    tipo = Column(SQLEnum(TipoTarifa), nullable=False)
    valor = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    estado = Column(SQLEnum(EstadoTarifa), default=EstadoTarifa.PENDENTE, nullable=False)
    data = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    conta = relationship("Conta", back_populates="tarifas")
