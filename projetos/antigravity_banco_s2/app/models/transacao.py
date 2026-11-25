from decimal import Decimal
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import TipoTransacao, EstadoTransacao, get_current_time


class Transacao(Base):
    __tablename__ = "transacoes"

    id = Column(Integer, primary_key=True, index=True)
    conta_id = Column(Integer, ForeignKey("contas.id"), nullable=False, index=True)
    conta_destino_id = Column(Integer, ForeignKey("contas.id"), nullable=True, index=True)
    tipo = Column(
        SQLEnum(TipoTransacao, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    valor = Column(Numeric(14, 2), nullable=False)
    data = Column(DateTime, default=get_current_time, nullable=False, index=True)
    estado = Column(
        SQLEnum(EstadoTransacao, values_callable=lambda x: [e.value for e in x]),
        default=EstadoTransacao.EFETIVADA,
        nullable=False,
    )
    transacao_origem_id = Column(Integer, ForeignKey("transacoes.id"), nullable=True)
    descricao = Column(String(255), nullable=True)

    conta = relationship("Conta", foreign_keys=[conta_id], back_populates="transacoes")
    conta_destino = relationship("Conta", foreign_keys=[conta_destino_id])
    transacao_origem = relationship("Transacao", remote_side=[id])
