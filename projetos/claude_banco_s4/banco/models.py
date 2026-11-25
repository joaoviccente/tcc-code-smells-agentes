from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .enums import (
    Categoria,
    EstadoCartao,
    EstadoConta,
    EstadoFatura,
    EstadoTarifa,
    EstadoTransacao,
    MotivoBloqueioCartao,
    SituacaoCliente,
    TipoConta,
    TipoTarifa,
    TipoTransacao,
)

CENTAVO = Decimal("0.01")


class Dinheiro(TypeDecorator):
    """Valor monetario exato: Decimal na aplicacao, inteiro (centavos) no banco."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return int((Decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (Decimal(int(value)) / 100).quantize(CENTAVO)


def _enum(cls):
    return Enum(cls, native_enum=False, length=40, values_callable=lambda e: [m.value for m in e])


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
    cpf: Mapped[str] = mapped_column(String(11), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    categoria: Mapped[Categoria] = mapped_column(_enum(Categoria))
    situacao: Mapped[SituacaoCliente] = mapped_column(_enum(SituacaoCliente), default=SituacaoCliente.ATIVO)
    criado_em: Mapped[datetime] = mapped_column(DateTime)

    contas: Mapped[list["Conta"]] = relationship(back_populates="cliente")


class Conta(Base):
    __tablename__ = "contas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    tipo: Mapped[TipoConta] = mapped_column(_enum(TipoConta))
    saldo: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    limite_credito: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    estado: Mapped[EstadoConta] = mapped_column(_enum(EstadoConta), default=EstadoConta.ATIVA)
    negativo_desde: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime)
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cliente: Mapped[Cliente] = relationship(back_populates="contas")
    cartoes: Mapped[list["Cartao"]] = relationship(back_populates="conta")


class Transacao(Base):
    __tablename__ = "transacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    conta_destino_id: Mapped[int | None] = mapped_column(ForeignKey("contas.id"), nullable=True, index=True)
    tipo: Mapped[TipoTransacao] = mapped_column(_enum(TipoTransacao))
    valor: Mapped[Decimal] = mapped_column(Dinheiro)
    data: Mapped[datetime] = mapped_column(DateTime, index=True)
    estado: Mapped[EstadoTransacao] = mapped_column(_enum(EstadoTransacao))
    transacao_original_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)

    conta: Mapped[Conta] = relationship(foreign_keys=[conta_id])
    conta_destino: Mapped[Conta | None] = relationship(foreign_keys=[conta_destino_id])


class Cartao(Base):
    __tablename__ = "cartoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    numero: Mapped[str] = mapped_column(String(16), unique=True)
    limite: Mapped[Decimal] = mapped_column(Dinheiro)
    estado: Mapped[EstadoCartao] = mapped_column(_enum(EstadoCartao), default=EstadoCartao.ATIVO)
    motivo_bloqueio: Mapped[MotivoBloqueioCartao | None] = mapped_column(_enum(MotivoBloqueioCartao), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime)

    conta: Mapped[Conta] = relationship(back_populates="cartoes")
    faturas: Mapped[list["Fatura"]] = relationship(back_populates="cartao")


class Fatura(Base):
    __tablename__ = "faturas"
    __table_args__ = (UniqueConstraint("cartao_id", "mes_referencia", name="uq_fatura_cartao_mes"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cartao_id: Mapped[int] = mapped_column(ForeignKey("cartoes.id"), index=True)
    mes_referencia: Mapped[str] = mapped_column(String(7))  # AAAA-MM
    valor: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    juros: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    vencimento: Mapped[date] = mapped_column(Date)
    estado: Mapped[EstadoFatura] = mapped_column(_enum(EstadoFatura), default=EstadoFatura.ABERTA)
    data_pagamento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valor_pago: Mapped[Decimal | None] = mapped_column(Dinheiro, nullable=True)

    cartao: Mapped[Cartao] = relationship(back_populates="faturas")

    @property
    def valor_total(self) -> Decimal:
        return (self.valor or Decimal("0")) + (self.juros or Decimal("0"))


class Tarifa(Base):
    __tablename__ = "tarifas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    tipo: Mapped[TipoTarifa] = mapped_column(_enum(TipoTarifa))
    valor: Mapped[Decimal] = mapped_column(Dinheiro)
    estado: Mapped[EstadoTarifa] = mapped_column(_enum(EstadoTarifa))
    competencia: Mapped[str] = mapped_column(String(7), index=True)  # AAAA-MM
    data: Mapped[datetime] = mapped_column(DateTime)
    data_cobranca: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    transacao_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)

    conta: Mapped[Conta] = relationship()
