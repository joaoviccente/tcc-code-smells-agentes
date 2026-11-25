from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import TipoTransacao, EstadoTransacao


class Transacao(Base):
    __tablename__ = "transacoes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conta_id = Column(Integer, ForeignKey("contas.id"), nullable=False, index=True)
    conta_destino_id = Column(Integer, ForeignKey("contas.id"), nullable=True, index=True)
    transacao_origem_id = Column(Integer, ForeignKey("transacoes.id"), nullable=True, index=True)
    tipo = Column(SQLEnum(TipoTransacao), nullable=False)
    valor = Column(Numeric(14, 2), nullable=False)
    data = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    estado = Column(SQLEnum(EstadoTransacao), default=EstadoTransacao.EFETIVADA, nullable=False)
    descricao = Column(String(255), nullable=True)

    conta = relationship("Conta", foreign_keys=[conta_id], back_populates="transacoes")
    conta_destino = relationship("Conta", foreign_keys=[conta_destino_id])
    transacao_origem = relationship("Transacao", remote_side=[id])
