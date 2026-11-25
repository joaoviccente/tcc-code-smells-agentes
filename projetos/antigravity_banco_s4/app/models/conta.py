from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, Enum as SQLEnum, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import TipoConta, EstadoConta


class Conta(Base):
    __tablename__ = "contas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    numero = Column(String(20), unique=True, index=True, nullable=False)
    tipo = Column(SQLEnum(TipoConta), default=TipoConta.CORRENTE, nullable=False)
    saldo = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    limite_de_credito = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    estado = Column(SQLEnum(EstadoConta), default=EstadoConta.ATIVA, nullable=False)
    data_saldo_negativo_inicio = Column(DateTime, nullable=True)
    data_criacao = Column(DateTime, default=datetime.utcnow, nullable=False)

    cliente = relationship("Cliente", back_populates="contas")
    cartoes = relationship("Cartao", back_populates="conta", cascade="all, delete-orphan")
    transacoes = relationship(
        "Transacao",
        primaryjoin="Conta.id == Transacao.conta_id",
        back_populates="conta",
        cascade="all, delete-orphan",
    )
    tarifas = relationship("Tarifa", back_populates="conta", cascade="all, delete-orphan")
