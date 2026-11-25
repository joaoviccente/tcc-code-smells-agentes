from sqlalchemy import Column, Integer, String, Enum as SQLEnum, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import EstadoTarifa, get_current_time


class Tarifa(Base):
    __tablename__ = "tarifas"

    id = Column(Integer, primary_key=True, index=True)
    conta_id = Column(Integer, ForeignKey("contas.id"), nullable=False, index=True)
    tipo = Column(String(50), nullable=False)
    valor = Column(Numeric(14, 2), nullable=False)
    data = Column(DateTime, default=get_current_time, nullable=False, index=True)
    estado = Column(
        SQLEnum(EstadoTarifa, values_callable=lambda x: [e.value for e in x]),
        default=EstadoTarifa.COBRADA,
        nullable=False,
    )

    conta = relationship("Conta", back_populates="tarifas")
