from sqlalchemy import Column, Integer, String, Enum as SQLEnum, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import TipoTransacao, EstadoTransacao
from app.utils import utc_now


class Transacao(Base):
    __tablename__ = "transacoes"

    id = Column(Integer, primary_key=True, index=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False)
    conta_destino_id = Column(Integer, ForeignKey("contas.id", ondelete="SET NULL"), nullable=True)
    tipo = Column(SQLEnum(TipoTransacao), nullable=False)
    valor = Column(Numeric(14, 2), nullable=False)
    data = Column(DateTime, default=utc_now, nullable=False)
    estado = Column(SQLEnum(EstadoTransacao), default=EstadoTransacao.PENDENTE, nullable=False)
    transacao_origem_id = Column(Integer, ForeignKey("transacoes.id", ondelete="SET NULL"), nullable=True)
    descricao = Column(String(255), nullable=True)

    conta = relationship("Conta", foreign_keys=[conta_id], back_populates="transacoes")
    conta_destino = relationship("Conta", foreign_keys=[conta_destino_id])
    transacao_origem = relationship("Transacao", remote_side=[id], backref="estornos")
