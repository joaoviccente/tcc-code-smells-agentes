import enum
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app import clock
from app.database import Base

CENTAVO = Decimal("0.01")


def arredondar(valor) -> Decimal:
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class Dinheiro(TypeDecorator):
    """Armazena valores monetarios como inteiro de centavos (exato) e expoe Decimal."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return int((Decimal(value) * 100).to_integral_value(rounding=ROUND_HALF_UP))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (Decimal(int(value)) / 100).quantize(CENTAVO)


# ---------------------------------------------------------------- enums
class CategoriaCliente(enum.StrEnum):
    COMUM = "comum"
    PREMIUM = "premium"
    EMPRESARIAL = "empresarial"


class SituacaoCliente(enum.StrEnum):
    ATIVO = "ativo"
    BLOQUEADO = "bloqueado"


class TipoConta(enum.StrEnum):
    CORRENTE = "corrente"
    POUPANCA = "poupanca"


class EstadoConta(enum.StrEnum):
    ATIVA = "ativa"
    BLOQUEADA = "bloqueada"
    ENCERRADA = "encerrada"


class TipoTransacao(enum.StrEnum):
    DEPOSITO = "deposito"
    SAQUE = "saque"
    TRANSFERENCIA = "transferencia"
    ESTORNO = "estorno"


class EstadoTransacao(enum.StrEnum):
    PENDENTE = "pendente"
    EFETIVADA = "efetivada"
    ESTORNADA = "estornada"


class EstadoCartao(enum.StrEnum):
    ATIVO = "ativo"
    BLOQUEADO = "bloqueado"
    CANCELADO = "cancelado"


class MotivoBloqueioCartao(enum.StrEnum):
    MANUAL = "manual"
    ATRASO_FATURA = "atraso_fatura"
    SALDO_NEGATIVO = "saldo_negativo"


class EstadoFatura(enum.StrEnum):
    ABERTA = "aberta"
    FECHADA = "fechada"
    PAGA = "paga"
    ATRASADA = "atrasada"


class TipoTarifa(enum.StrEnum):
    MENSAL = "mensal"
    TRANSACAO = "transacao"


class EstadoTarifa(enum.StrEnum):
    PENDENTE = "pendente"
    COBRADA = "cobrada"
    ISENTA = "isenta"


def _enum(e):
    return SAEnum(e, native_enum=False, length=20, values_callable=lambda x: [m.value for m in x])


# --------------------------------------------------------------- tabelas
class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    cpf: Mapped[str] = mapped_column(String(11), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    categoria: Mapped[CategoriaCliente] = mapped_column(_enum(CategoriaCliente))
    situacao: Mapped[SituacaoCliente] = mapped_column(
        _enum(SituacaoCliente), default=SituacaoCliente.ATIVO
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=lambda: clock.agora())

    contas: Mapped[list["Conta"]] = relationship(back_populates="cliente")


class Conta(Base):
    __tablename__ = "contas"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    tipo: Mapped[TipoConta] = mapped_column(_enum(TipoConta))
    saldo: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    limite_credito: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    estado: Mapped[EstadoConta] = mapped_column(_enum(EstadoConta), default=EstadoConta.ATIVA)
    # momento em que o saldo ficou negativo (None se saldo >= 0) - base da regra 6
    negativo_desde: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=lambda: clock.agora())
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cliente: Mapped[Cliente] = relationship(back_populates="contas")
    cartoes: Mapped[list["Cartao"]] = relationship(back_populates="conta")
    tarifas: Mapped[list["Tarifa"]] = relationship(back_populates="conta")


class Transacao(Base):
    __tablename__ = "transacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    conta_destino_id: Mapped[int | None] = mapped_column(
        ForeignKey("contas.id"), nullable=True, index=True
    )
    tipo: Mapped[TipoTransacao] = mapped_column(_enum(TipoTransacao))
    valor: Mapped[Decimal] = mapped_column(Dinheiro)
    data: Mapped[datetime] = mapped_column(DateTime, index=True)
    estado: Mapped[EstadoTransacao] = mapped_column(_enum(EstadoTransacao))
    transacao_original_id: Mapped[int | None] = mapped_column(
        ForeignKey("transacoes.id"), nullable=True
    )
    descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)

    conta: Mapped[Conta] = relationship(foreign_keys=[conta_id])
    conta_destino: Mapped[Conta | None] = relationship(foreign_keys=[conta_destino_id])
    original: Mapped["Transacao | None"] = relationship(remote_side=[id])
    tarifa: Mapped["Tarifa | None"] = relationship(back_populates="transacao", uselist=False)


class Cartao(Base):
    __tablename__ = "cartoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    numero: Mapped[str] = mapped_column(String(16), unique=True)
    limite: Mapped[Decimal] = mapped_column(Dinheiro)
    estado: Mapped[EstadoCartao] = mapped_column(_enum(EstadoCartao), default=EstadoCartao.ATIVO)
    motivo_bloqueio: Mapped[MotivoBloqueioCartao | None] = mapped_column(
        _enum(MotivoBloqueioCartao), nullable=True
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=lambda: clock.agora())

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
    data_pagamento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valor_pago: Mapped[Decimal | None] = mapped_column(Dinheiro, nullable=True)

    cartao: Mapped[Cartao] = relationship(back_populates="faturas")

    @property
    def valor_total(self) -> Decimal:
        return arredondar(self.valor + (self.juros or 0))

    @property
    def dias_atraso(self) -> int:
        if self.estado != EstadoFatura.ATRASADA:
            return 0
        return max(0, (clock.agora().date() - self.data_vencimento).days)


class Tarifa(Base):
    __tablename__ = "tarifas"

    id: Mapped[int] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    tipo: Mapped[TipoTarifa] = mapped_column(_enum(TipoTarifa))
    valor: Mapped[Decimal] = mapped_column(Dinheiro)
    estado: Mapped[EstadoTarifa] = mapped_column(_enum(EstadoTarifa))
    # categoria do cliente no momento da geracao (base do relatorio de receita)
    categoria: Mapped[CategoriaCliente] = mapped_column(_enum(CategoriaCliente))
    competencia: Mapped[str] = mapped_column(String(7), index=True)  # AAAA-MM
    transacao_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime)
    cobrada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    conta: Mapped[Conta] = relationship(back_populates="tarifas")
    transacao: Mapped[Transacao | None] = relationship(back_populates="tarifa")
