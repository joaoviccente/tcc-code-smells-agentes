from sqlalchemy import Column, Integer, String, Enum as SQLEnum, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import EstadoTarifa, TipoTarifa
from app.utils import utc_now


class Tarifa(Base):
    __tablename__ = "tarifas"

    id = Column(Integer, primary_key=True, index=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False)
    tipo = Column(SQLEnum(TipoTarifa), nullable=False)
    valor = Column(Numeric(14, 2), nullable=False)
    estado = Column(SQLEnum(EstadoTarifa), default=EstadoTarifa.PENDENTE, nullable=False)
    data = Column(DateTime, default=utc_now, nullable=False)

    conta = relationship("Conta", back_populates="tarifas")
