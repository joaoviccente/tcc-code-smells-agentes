from decimal import Decimal
import enum
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class EstadoTarifa(str, enum.Enum):
    PENDENTE = "pendente"
    COBRADA = "cobrada"
    ISENTA = "isenta"


class Tarifa(Base):
    __tablename__ = "tarifas"

    id = Column(Integer, primary_key=True, index=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo = Column(String(50), nullable=False)  # mensalidade, transferencia, etc.
    valor = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    estado = Column(
        Enum(EstadoTarifa, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=EstadoTarifa.COBRADA,
    )
    descricao = Column(String(255), nullable=True)
    data = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    conta = relationship("Conta", back_populates="tarifas")
