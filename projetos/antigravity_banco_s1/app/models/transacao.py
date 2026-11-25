from decimal import Decimal
import enum
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class TipoTransacao(str, enum.Enum):
    DEPOSITO = "deposito"
    SAQUE = "saque"
    TRANSFERENCIA = "transferencia"
    ESTORNO = "estorno"


class EstadoTransacao(str, enum.Enum):
    PENDENTE = "pendente"
    EFETIVADA = "efetivada"
    ESTORNADA = "estornada"


class Transacao(Base):
    __tablename__ = "transacoes"

    id = Column(Integer, primary_key=True, index=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False, index=True)
    conta_destino_id = Column(Integer, ForeignKey("contas.id", ondelete="SET NULL"), nullable=True, index=True)
    tipo = Column(
        Enum(TipoTransacao, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    valor = Column(Numeric(14, 2), nullable=False)
    data = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    estado = Column(
        Enum(EstadoTransacao, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=EstadoTransacao.EFETIVADA,
    )
    transacao_origem_id = Column(
        Integer, ForeignKey("transacoes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    descricao = Column(String(255), nullable=True)

    conta = relationship("Conta", back_populates="transacoes_origem", foreign_keys=[conta_id])
    conta_destino = relationship("Conta", back_populates="transacoes_destino", foreign_keys=[conta_destino_id])
    transacao_origem = relationship("Transacao", remote_side=[id])
