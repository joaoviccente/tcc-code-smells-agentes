from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Index,
    String, TypeDecorator, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import (
    CategoriaCliente, EstadoCartao, EstadoConta, EstadoFatura, EstadoTarifa,
    EstadoTransacao, SituacaoCliente, TipoConta, TipoTarifa, TipoTransacao,
)

CENTAVO = Decimal("0.01")


class Dinheiro(TypeDecorator):
    """Valor monetario armazenado como inteiro em centavos (exato)."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return int((Decimal(value).quantize(CENTAVO, ROUND_HALF_UP) * 100).to_integral_value())

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (Decimal(value) / 100).quantize(CENTAVO)


def _enum(e):
    return SAEnum(e, values_callable=lambda x: [m.value for m in x], native_enum=False,
                  validate_strings=True, length=20)


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    cpf: Mapped[str] = mapped_column(String(11), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    categoria: Mapped[CategoriaCliente] = mapped_column(_enum(CategoriaCliente))
    situacao: Mapped[SituacaoCliente] = mapped_column(_enum(SituacaoCliente), default=SituacaoCliente.ATIVO)
    criado_em: Mapped[datetime] = mapped_column(DateTime)

    contas: Mapped[list["Conta"]] = relationship(back_populates="cliente")


class Conta(Base):
    __tablename__ = "contas"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    tipo: Mapped[TipoConta] = mapped_column(_enum(TipoConta))
    saldo: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    limite_credito: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    estado: Mapped[EstadoConta] = mapped_column(_enum(EstadoConta), default=EstadoConta.ATIVA)
    # Momento em que o saldo ficou negativo (None quando saldo >= 0) - regra 6
    negativo_desde: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime)
    encerrada_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    cliente: Mapped[Cliente] = relationship(back_populates="contas")
    cartoes: Mapped[list["Cartao"]] = relationship(back_populates="conta")


class Transacao(Base):
    __tablename__ = "transacoes"
    __table_args__ = (
        Index("ix_transacoes_conta_data", "conta_id", "data"),
        Index("ix_transacoes_destino_data", "conta_destino_id", "data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))
    # Somente para transferencias (e estornos de transferencias)
    conta_destino_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contas.id"), nullable=True)
    tipo: Mapped[TipoTransacao] = mapped_column(_enum(TipoTransacao))
    valor: Mapped[Decimal] = mapped_column(Dinheiro)
    data: Mapped[datetime] = mapped_column(DateTime)
    estado: Mapped[EstadoTransacao] = mapped_column(_enum(EstadoTransacao))
    descricao: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # Para estornos: transacao que foi estornada
    transacao_original_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transacoes.id"), nullable=True, unique=True)
    # Indica se a transacao consumiu a franquia de transacoes isentas (regra 3)
    consome_franquia: Mapped[bool] = mapped_column(Boolean, default=False)


class Cartao(Base):
    __tablename__ = "cartoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    limite: Mapped[Decimal] = mapped_column(Dinheiro)
    estado: Mapped[EstadoCartao] = mapped_column(_enum(EstadoCartao), default=EstadoCartao.ATIVO)
    criado_em: Mapped[datetime] = mapped_column(DateTime)

    conta: Mapped[Conta] = relationship(back_populates="cartoes")
    faturas: Mapped[list["Fatura"]] = relationship(back_populates="cartao")


class Fatura(Base):
    __tablename__ = "faturas"
    __table_args__ = (UniqueConstraint("cartao_id", "mes_referencia"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cartao_id: Mapped[int] = mapped_column(ForeignKey("cartoes.id"), index=True)
    mes_referencia: Mapped[str] = mapped_column(String(7))  # AAAA-MM
    valor: Mapped[Decimal] = mapped_column(Dinheiro)
    juros: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    data_vencimento: Mapped[date] = mapped_column(Date)
    estado: Mapped[EstadoFatura] = mapped_column(_enum(EstadoFatura), default=EstadoFatura.ABERTA)
    data_pagamento: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    valor_pago: Mapped[Optional[Decimal]] = mapped_column(Dinheiro, nullable=True)

    cartao: Mapped[Cartao] = relationship(back_populates="faturas")

    @property
    def valor_total(self) -> Decimal:
        return (self.valor + (self.juros or Decimal("0"))).quantize(CENTAVO)


class Tarifa(Base):
    __tablename__ = "tarifas"
    __table_args__ = (Index("ix_tarifas_conta_tipo_mes", "conta_id", "tipo", "mes_referencia"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))
    tipo: Mapped[TipoTarifa] = mapped_column(_enum(TipoTarifa))
    valor: Mapped[Decimal] = mapped_column(Dinheiro)
    estado: Mapped[EstadoTarifa] = mapped_column(_enum(EstadoTarifa))
    mes_referencia: Mapped[str] = mapped_column(String(7))
    # Categoria do cliente no momento da geracao (para relatorio de receita)
    categoria_cliente: Mapped[CategoriaCliente] = mapped_column(_enum(CategoriaCliente))
    transacao_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime)
    cobrada_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
