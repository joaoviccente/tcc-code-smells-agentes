from decimal import Decimal
import enum
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class TipoConta(str, enum.Enum):
    CORRENTE = "corrente"
    POUPANCA = "poupanca"


class EstadoConta(str, enum.Enum):
    ATIVA = "ativa"
    BLOQUEADA = "bloqueada"
    ENCERRADA = "encerrada"


class Conta(Base):
    __tablename__ = "contas"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    numero = Column(String(30), unique=True, nullable=False, index=True)
    tipo = Column(
        Enum(TipoConta, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=TipoConta.CORRENTE,
    )
    saldo = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    limite_credito = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    estado = Column(
        Enum(EstadoConta, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=EstadoConta.ATIVA,
    )
    data_saldo_negativo = Column(DateTime, nullable=True)
    data_criacao = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    cliente = relationship("Cliente", back_populates="contas")
    cartoes = relationship("Cartao", back_populates="conta", cascade="all, delete-orphan")
    transacoes_origem = relationship(
        "Transacao",
        back_populates="conta",
        foreign_keys="Transacao.conta_id",
        cascade="all, delete-orphan",
    )
    transacoes_destino = relationship(
        "Transacao",
        back_populates="conta_destino",
        foreign_keys="Transacao.conta_destino_id",
    )
    tarifas = relationship("Tarifa", back_populates="conta", cascade="all, delete-orphan")
