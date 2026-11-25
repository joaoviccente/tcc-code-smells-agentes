from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, Dinheiro

CATEGORIAS = ("comum", "premium", "empresarial")
SITUACOES_CLIENTE = ("ativo", "bloqueado")
TIPOS_CONTA = ("corrente", "poupanca")
ESTADOS_CONTA = ("ativa", "bloqueada", "encerrada")
TIPOS_TRANSACAO = ("deposito", "saque", "transferencia", "estorno")
ESTADOS_TRANSACAO = ("pendente", "efetivada", "estornada")
ESTADOS_CARTAO = ("ativo", "bloqueado", "cancelado")
ESTADOS_FATURA = ("aberta", "fechada", "paga", "atrasada")
TIPOS_TARIFA = ("mensalidade", "transacao")
ESTADOS_TARIFA = ("pendente", "cobrada", "isenta")


def _in(coluna: str, valores: tuple[str, ...]) -> str:
    return f"{coluna} IN ({', '.join(repr(v) for v in valores)})"


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (
        CheckConstraint(_in("categoria", CATEGORIAS), name="ck_cliente_categoria"),
        CheckConstraint(_in("situacao", SITUACOES_CLIENTE), name="ck_cliente_situacao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    cpf: Mapped[str] = mapped_column(String(11), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    categoria: Mapped[str] = mapped_column(String(20))
    situacao: Mapped[str] = mapped_column(String(20), default="ativo")
    criado_em: Mapped[datetime] = mapped_column(DateTime)

    contas: Mapped[list["Conta"]] = relationship(back_populates="cliente")


class Conta(Base):
    __tablename__ = "contas"
    __table_args__ = (
        CheckConstraint(_in("tipo", TIPOS_CONTA), name="ck_conta_tipo"),
        CheckConstraint(_in("estado", ESTADOS_CONTA), name="ck_conta_estado"),
        CheckConstraint("limite_credito >= 0", name="ck_conta_limite"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    saldo: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    limite_credito: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    estado: Mapped[str] = mapped_column(String(20), default="ativa")
    # Momento em que o saldo ficou negativo (None quando saldo >= 0) - regra 6.
    negativo_desde: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime)
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cliente: Mapped[Cliente] = relationship(back_populates="contas")
    cartoes: Mapped[list["Cartao"]] = relationship(back_populates="conta")


class Transacao(Base):
    __tablename__ = "transacoes"
    __table_args__ = (
        CheckConstraint(_in("tipo", TIPOS_TRANSACAO), name="ck_transacao_tipo"),
        CheckConstraint(_in("estado", ESTADOS_TRANSACAO), name="ck_transacao_estado"),
        CheckConstraint("valor > 0", name="ck_transacao_valor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    conta_destino_id: Mapped[int | None] = mapped_column(ForeignKey("contas.id"), index=True, nullable=True)
    tipo: Mapped[str] = mapped_column(String(20))
    valor: Mapped[Decimal] = mapped_column(Dinheiro)
    data: Mapped[datetime] = mapped_column(DateTime, index=True)
    estado: Mapped[str] = mapped_column(String(20))
    transacao_original_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    descricao: Mapped[str | None] = mapped_column(String(200), nullable=True)

    conta: Mapped[Conta] = relationship(foreign_keys=[conta_id])
    conta_destino: Mapped[Conta | None] = relationship(foreign_keys=[conta_destino_id])
    transacao_original: Mapped["Transacao | None"] = relationship(remote_side=[id])


class Cartao(Base):
    __tablename__ = "cartoes"
    __table_args__ = (
        CheckConstraint(_in("estado", ESTADOS_CARTAO), name="ck_cartao_estado"),
        CheckConstraint("limite >= 0", name="ck_cartao_limite"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    limite: Mapped[Decimal] = mapped_column(Dinheiro)
    estado: Mapped[str] = mapped_column(String(20), default="ativo")
    criado_em: Mapped[datetime] = mapped_column(DateTime)

    conta: Mapped[Conta] = relationship(back_populates="cartoes")
    faturas: Mapped[list["Fatura"]] = relationship(back_populates="cartao")


class Fatura(Base):
    __tablename__ = "faturas"
    __table_args__ = (
        CheckConstraint(_in("estado", ESTADOS_FATURA), name="ck_fatura_estado"),
        CheckConstraint("valor >= 0", name="ck_fatura_valor"),
        UniqueConstraint("cartao_id", "mes_referencia", name="uq_fatura_cartao_mes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cartao_id: Mapped[int] = mapped_column(ForeignKey("cartoes.id"), index=True)
    mes_referencia: Mapped[str] = mapped_column(String(7))  # AAAA-MM
    valor: Mapped[Decimal] = mapped_column(Dinheiro)
    juros: Mapped[Decimal] = mapped_column(Dinheiro, default=Decimal("0.00"))
    vencimento: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="aberta")
    pago_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valor_pago: Mapped[Decimal | None] = mapped_column(Dinheiro, nullable=True)

    cartao: Mapped[Cartao] = relationship(back_populates="faturas")

    @property
    def total_devido(self) -> Decimal:
        if self.estado == "paga":
            return Decimal("0.00")
        return self.valor + (self.juros or Decimal("0.00"))


class Tarifa(Base):
    __tablename__ = "tarifas"
    __table_args__ = (
        CheckConstraint(_in("tipo", TIPOS_TARIFA), name="ck_tarifa_tipo"),
        CheckConstraint(_in("estado", ESTADOS_TARIFA), name="ck_tarifa_estado"),
        CheckConstraint("valor >= 0", name="ck_tarifa_valor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("contas.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    valor: Mapped[Decimal] = mapped_column(Dinheiro)
    estado: Mapped[str] = mapped_column(String(20))
    mes_referencia: Mapped[str] = mapped_column(String(7), index=True)  # AAAA-MM
    transacao_id: Mapped[int | None] = mapped_column(ForeignKey("transacoes.id"), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime)
    cobrada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    conta: Mapped[Conta] = relationship()
