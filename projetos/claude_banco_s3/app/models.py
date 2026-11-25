import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.money import Money


class CategoriaCliente(str, enum.Enum):
    COMUM = "comum"
    PREMIUM = "premium"
    EMPRESARIAL = "empresarial"


class SituacaoCliente(str, enum.Enum):
    ATIVO = "ativo"
    BLOQUEADO = "bloqueado"


class TipoConta(str, enum.Enum):
    CORRENTE = "corrente"
    POUPANCA = "poupanca"


class EstadoConta(str, enum.Enum):
    ATIVA = "ativa"
    BLOQUEADA = "bloqueada"
    ENCERRADA = "encerrada"


class TipoTransacao(str, enum.Enum):
    DEPOSITO = "deposito"
    SAQUE = "saque"
    TRANSFERENCIA = "transferencia"
    ESTORNO = "estorno"


class EstadoTransacao(str, enum.Enum):
    PENDENTE = "pendente"
    EFETIVADA = "efetivada"
    ESTORNADA = "estornada"


class EstadoCartao(str, enum.Enum):
    ATIVO = "ativo"
    BLOQUEADO = "bloqueado"
    CANCELADO = "cancelado"


class EstadoFatura(str, enum.Enum):
    ABERTA = "aberta"
    FECHADA = "fechada"
    PAGA = "paga"
    ATRASADA = "atrasada"


class TipoTarifa(str, enum.Enum):
    MENSAL = "mensal"
    TRANSACAO = "transacao"


class EstadoTarifa(str, enum.Enum):
    PENDENTE = "pendente"
    COBRADA = "cobrada"
    ISENTA = "isenta"


def _enum(e):
    return Enum(e, native_enum=False, length=20, values_callable=lambda x: [m.value for m in x],
                validate_strings=True)


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    cpf: Mapped[str] = mapped_column(String(11), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254))
    categoria: Mapped[CategoriaCliente] = mapped_column(_enum(CategoriaCliente))
    situacao: Mapped[SituacaoCliente] = mapped_column(_enum(SituacaoCliente), default=SituacaoCliente.ATIVO)
    criado_em: Mapped[datetime] = mapped_column(DateTime)

    contas: Mapped[list["Conta"]] = relationship(back_populates="cliente", order_by="Conta.id")


class Conta(Base):
    __tablename__ = "contas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    tipo: Mapped[TipoConta] = mapped_column(_enum(TipoConta))
    saldo: Mapped[Decimal] = mapped_column(Money)
    limite_credito: Mapped[Decimal] = mapped_column(Money)
    estado: Mapped[EstadoConta] = mapped_column(_enum(EstadoConta))
    # Momento em que o saldo ficou negativo (None se saldo >= 0). Base da regra 6.
    negativo_desde: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime)
    encerrado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cliente: Mapped[Cliente] = relationship(back_populates="contas")
    cartoes: Mapped[list["Cartao"]] = relationship(back_populates="conta", order_by="Cartao.id")

    @property
    def saldo_disponivel(self) -> Decimal:
        return self.saldo + self.limite_credito


class Transacao(Base):
    __tablename__ = "transacoes"
    __table_args__ = (
        Index("ix_transacoes_conta_data", "conta_id", "data"),
        Index("ix_transacoes_destino_data", "conta_destino_id", "data"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))
    conta_destino_id: Mapped[int | None] = mapped_column(ForeignKey("contas.id"), nullable=True)
    tipo: Mapped[TipoTransacao] = mapped_column(_enum(TipoTransacao))
    valor: Mapped[Decimal] = mapped_column(Money)
    data: Mapped[datetime] = mapped_column(DateTime)
    estado: Mapped[EstadoTransacao] = mapped_column(_enum(EstadoTransacao))
    descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)
    transacao_original_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)

    conta: Mapped[Conta] = relationship(foreign_keys=[conta_id])
    conta_destino: Mapped[Conta | None] = relationship(foreign_keys=[conta_destino_id])
    transacao_original: Mapped["Transacao | None"] = relationship(remote_side=[id])


class Cartao(Base):
    __tablename__ = "cartoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    numero: Mapped[str] = mapped_column(String(16), unique=True)
    limite: Mapped[Decimal] = mapped_column(Money)
    estado: Mapped[EstadoCartao] = mapped_column(_enum(EstadoCartao))
    motivo_bloqueio: Mapped[str | None] = mapped_column(String(40), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime)

    conta: Mapped[Conta] = relationship(back_populates="cartoes")
    faturas: Mapped[list["Fatura"]] = relationship(back_populates="cartao", order_by="Fatura.mes_referencia")


class Fatura(Base):
    __tablename__ = "faturas"
    __table_args__ = (UniqueConstraint("cartao_id", "mes_referencia", name="uq_fatura_cartao_mes"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cartao_id: Mapped[int] = mapped_column(ForeignKey("cartoes.id"), index=True)
    mes_referencia: Mapped[str] = mapped_column(String(7))  # AAAA-MM
    valor_original: Mapped[Decimal] = mapped_column(Money)
    juros: Mapped[Decimal] = mapped_column(Money)
    valor: Mapped[Decimal] = mapped_column(Money)  # valor_original + juros
    data_vencimento: Mapped[date] = mapped_column(Date)
    estado: Mapped[EstadoFatura] = mapped_column(_enum(EstadoFatura))
    data_pagamento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valor_pago: Mapped[Decimal | None] = mapped_column(Money, nullable=True)

    cartao: Mapped[Cartao] = relationship(back_populates="faturas")


class Tarifa(Base):
    __tablename__ = "tarifas"
    __table_args__ = (Index("ix_tarifas_conta_tipo_comp", "conta_id", "tipo", "competencia"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"))
    tipo: Mapped[TipoTarifa] = mapped_column(_enum(TipoTarifa))
    valor: Mapped[Decimal] = mapped_column(Money)
    estado: Mapped[EstadoTarifa] = mapped_column(_enum(EstadoTarifa))
    # Categoria do cliente no momento da geracao (base do relatorio de receita).
    categoria_cliente: Mapped[CategoriaCliente] = mapped_column(_enum(CategoriaCliente))
    competencia: Mapped[str] = mapped_column(String(7))  # AAAA-MM
    transacao_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime)
    cobrado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    conta: Mapped[Conta] = relationship()
