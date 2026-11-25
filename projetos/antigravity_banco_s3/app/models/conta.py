from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import TipoConta, EstadoConta


class Conta(Base):
    __tablename__ = "contas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    numero = Column(String(20), unique=True, index=True, nullable=False)
    tipo = Column(SQLEnum(TipoConta), default=TipoConta.CORRENTE, nullable=False)
    saldo = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    limite_credito = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    estado = Column(SQLEnum(EstadoConta), default=EstadoConta.ATIVA, nullable=False)
    saldo_negativo_desde = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    cliente = relationship("Cliente", back_populates="contas")
    cartoes = relationship("Cartao", back_populates="conta", cascade="all, delete-orphan")
    transacoes = relationship(
        "Transacao",
        primaryjoin="Conta.id == Transacao.conta_id",
        back_populates="conta",
        cascade="all, delete-orphan",
    )
    tarifas = relationship("Tarifa", back_populates="conta", cascade="all, delete-orphan")
