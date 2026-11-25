from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import (
    Categoria,
    EstadoEmprestimo,
    EstadoExemplar,
    EstadoMulta,
    EstadoReserva,
    SituacaoUsuario,
)


def _enum(cls: type[PyEnum]) -> Enum:
    return Enum(cls, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e],
                validate_strings=True)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    matricula: Mapped[str] = mapped_column(String(30), unique=True)
    categoria: Mapped[Categoria] = mapped_column(_enum(Categoria))
    situacao: Mapped[SituacaoUsuario] = mapped_column(_enum(SituacaoUsuario), default=SituacaoUsuario.ATIVO)
    # Fim da suspensao automatica (regra 2). Nulo com situacao=suspenso => suspensao manual.
    suspenso_ate: Mapped[date | None] = mapped_column(Date, nullable=True)

    emprestimos: Mapped[list["Emprestimo"]] = relationship(back_populates="usuario")
    reservas: Mapped[list["Reserva"]] = relationship(back_populates="usuario")


class Livro(Base):
    __tablename__ = "livros"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(300))
    autor: Mapped[str] = mapped_column(String(200))
    isbn: Mapped[str] = mapped_column(String(13), unique=True)
    ano: Mapped[int] = mapped_column(Integer)
    area: Mapped[str] = mapped_column(String(100), index=True)

    exemplares: Mapped[list["Exemplar"]] = relationship(back_populates="livro")
    reservas: Mapped[list["Reserva"]] = relationship(back_populates="livro")


class Exemplar(Base):
    __tablename__ = "exemplares"

    id: Mapped[int] = mapped_column(primary_key=True)
    livro_id: Mapped[int] = mapped_column(ForeignKey("livros.id"), index=True)
    tombo: Mapped[str] = mapped_column(String(50), unique=True)
    estado: Mapped[EstadoExemplar] = mapped_column(_enum(EstadoExemplar), default=EstadoExemplar.DISPONIVEL)

    livro: Mapped[Livro] = relationship(back_populates="exemplares")
    emprestimos: Mapped[list["Emprestimo"]] = relationship(back_populates="exemplar")


class Emprestimo(Base):
    __tablename__ = "emprestimos"

    id: Mapped[int] = mapped_column(primary_key=True)
    exemplar_id: Mapped[int] = mapped_column(ForeignKey("exemplares.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    data_retirada: Mapped[datetime] = mapped_column(DateTime)
    data_prevista: Mapped[datetime] = mapped_column(DateTime)
    data_devolucao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estado: Mapped[EstadoEmprestimo] = mapped_column(_enum(EstadoEmprestimo), default=EstadoEmprestimo.ATIVO,
                                                     index=True)
    renovacoes: Mapped[int] = mapped_column(Integer, default=0)

    exemplar: Mapped[Exemplar] = relationship(back_populates="emprestimos")
    usuario: Mapped[Usuario] = relationship(back_populates="emprestimos")
    multa: Mapped["Multa | None"] = relationship(back_populates="emprestimo", uselist=False)


class Reserva(Base):
    __tablename__ = "reservas"

    id: Mapped[int] = mapped_column(primary_key=True)
    livro_id: Mapped[int] = mapped_column(ForeignKey("livros.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    data: Mapped[datetime] = mapped_column(DateTime)
    posicao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[EstadoReserva] = mapped_column(_enum(EstadoReserva), default=EstadoReserva.AGUARDANDO, index=True)
    # Preenchidos quando a reserva passa a "disponivel" (regra 4)
    exemplar_id: Mapped[int | None] = mapped_column(ForeignKey("exemplares.id"), nullable=True)
    disponivel_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    livro: Mapped[Livro] = relationship(back_populates="reservas")
    usuario: Mapped[Usuario] = relationship(back_populates="reservas")
    exemplar: Mapped[Exemplar | None] = relationship()


class Multa(Base):
    __tablename__ = "multas"
    __table_args__ = (UniqueConstraint("emprestimo_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    emprestimo_id: Mapped[int] = mapped_column(ForeignKey("emprestimos.id"))
    valor_centavos: Mapped[int] = mapped_column(Integer)
    dias_atraso: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoMulta] = mapped_column(_enum(EstadoMulta), default=EstadoMulta.ABERTA, index=True)
    data_pagamento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    emprestimo: Mapped[Emprestimo] = relationship(back_populates="multa")
