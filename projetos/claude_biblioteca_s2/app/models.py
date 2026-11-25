from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import relogio
from .database import Base
from .enums import (
    Categoria,
    EstadoEmprestimo,
    EstadoExemplar,
    EstadoMulta,
    EstadoReserva,
    SituacaoUsuario,
)


def _enum(tipo):
    return Enum(tipo, native_enum=False, validate_strings=True, length=20,
                values_callable=lambda e: [m.value for m in e])


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    matricula: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    categoria: Mapped[Categoria] = mapped_column(_enum(Categoria))
    situacao: Mapped[SituacaoUsuario] = mapped_column(_enum(SituacaoUsuario), default=SituacaoUsuario.ativo)
    # Data em que a suspensao automatica termina (usuario volta a ativo nesse dia).
    # None com situacao=suspenso significa suspensao manual por tempo indeterminado.
    suspensao_ate: Mapped[date | None] = mapped_column(Date, nullable=True)

    emprestimos: Mapped[list["Emprestimo"]] = relationship(back_populates="usuario")
    reservas: Mapped[list["Reserva"]] = relationship(back_populates="usuario")


class Livro(Base):
    __tablename__ = "livros"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(300))
    autor: Mapped[str] = mapped_column(String(200))
    isbn: Mapped[str] = mapped_column(String(13), unique=True, index=True)
    ano: Mapped[int] = mapped_column(Integer)
    area_conhecimento: Mapped[str] = mapped_column(String(100), index=True)

    exemplares: Mapped[list["Exemplar"]] = relationship(back_populates="livro")
    reservas: Mapped[list["Reserva"]] = relationship(back_populates="livro")


class Exemplar(Base):
    __tablename__ = "exemplares"

    id: Mapped[int] = mapped_column(primary_key=True)
    livro_id: Mapped[int] = mapped_column(ForeignKey("livros.id"), index=True)
    codigo_tombo: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    estado: Mapped[EstadoExemplar] = mapped_column(_enum(EstadoExemplar), default=EstadoExemplar.disponivel)

    livro: Mapped[Livro] = relationship(back_populates="exemplares")
    emprestimos: Mapped[list["Emprestimo"]] = relationship(back_populates="exemplar")


class Emprestimo(Base):
    __tablename__ = "emprestimos"
    __table_args__ = (CheckConstraint("renovacoes >= 0", name="ck_renovacoes_nao_negativas"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    exemplar_id: Mapped[int] = mapped_column(ForeignKey("exemplares.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    # Categoria do usuario no momento da retirada: define prazo, multa e renovacoes.
    categoria_usuario: Mapped[Categoria] = mapped_column(_enum(Categoria))
    data_retirada: Mapped[datetime] = mapped_column(DateTime)
    data_prevista: Mapped[date] = mapped_column(Date)
    data_devolucao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estado: Mapped[EstadoEmprestimo] = mapped_column(_enum(EstadoEmprestimo), default=EstadoEmprestimo.ativo)
    renovacoes: Mapped[int] = mapped_column(Integer, default=0)

    exemplar: Mapped[Exemplar] = relationship(back_populates="emprestimos")
    usuario: Mapped[Usuario] = relationship(back_populates="emprestimos")
    multa: Mapped["Multa | None"] = relationship(back_populates="emprestimo", uselist=False)

    @property
    def livro_id(self) -> int:
        return self.exemplar.livro_id

    @property
    def dias_atraso(self) -> int:
        """Dias corridos de atraso (ate a devolucao ou, se em aberto, ate hoje)."""
        fim = self.data_devolucao or relogio.agora()
        return max(0, (fim.date() - self.data_prevista).days)


class Reserva(Base):
    __tablename__ = "reservas"

    id: Mapped[int] = mapped_column(primary_key=True)
    livro_id: Mapped[int] = mapped_column(ForeignKey("livros.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    data_reserva: Mapped[datetime] = mapped_column(DateTime)
    # Posicao na fila (1 = primeiro). Nula quando a reserva saiu da fila.
    posicao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[EstadoReserva] = mapped_column(_enum(EstadoReserva), default=EstadoReserva.aguardando)
    # Exemplar separado para o usuario quando a reserva fica disponivel.
    exemplar_id: Mapped[int | None] = mapped_column(ForeignKey("exemplares.id"), nullable=True)
    disponivel_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    livro: Mapped[Livro] = relationship(back_populates="reservas")
    usuario: Mapped[Usuario] = relationship(back_populates="reservas")
    exemplar: Mapped[Exemplar | None] = relationship()


class Multa(Base):
    __tablename__ = "multas"
    __table_args__ = (CheckConstraint("valor_centavos >= 0", name="ck_valor_nao_negativo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    emprestimo_id: Mapped[int] = mapped_column(ForeignKey("emprestimos.id"), unique=True)
    valor_centavos: Mapped[int] = mapped_column(Integer)
    dias_atraso: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoMulta] = mapped_column(_enum(EstadoMulta), default=EstadoMulta.aberta)
    data_geracao: Mapped[datetime] = mapped_column(DateTime)
    data_pagamento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    emprestimo: Mapped[Emprestimo] = relationship(back_populates="multa")

    @property
    def valor(self) -> Decimal:
        return (Decimal(self.valor_centavos) / 100).quantize(Decimal("0.01"))

    @property
    def usuario_id(self) -> int:
        return self.emprestimo.usuario_id

    @property
    def valor_definitivo(self) -> bool:
        """O valor so e definitivo apos a devolucao (antes disso continua acumulando)."""
        return self.emprestimo.data_devolucao is not None
