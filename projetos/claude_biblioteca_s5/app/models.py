from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

CATEGORIAS = ("aluno", "professor", "visitante")
SITUACOES_USUARIO = ("ativo", "suspenso")
ESTADOS_EXEMPLAR = ("disponivel", "emprestado", "reservado", "em_reparo", "baixado")
ESTADOS_EMPRESTIMO = ("ativo", "devolvido", "atrasado")
# "atendida" e o estado terminal de uma reserva convertida em emprestimo.
ESTADOS_RESERVA = ("aguardando", "disponivel", "expirada", "cancelada", "atendida")
ESTADOS_MULTA = ("aberta", "paga", "perdoada")


def _in(col: str, valores: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in valores)})"


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint(_in("categoria", CATEGORIAS), name="ck_usuario_categoria"),
        CheckConstraint(_in("situacao", SITUACOES_USUARIO), name="ck_usuario_situacao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    matricula: Mapped[str] = mapped_column(String(50), unique=True)
    categoria: Mapped[str] = mapped_column(String(20))
    situacao: Mapped[str] = mapped_column(String(20), default="ativo")
    # Suspensao automatica (regra 2): data de termino; None enquanto o atraso persiste.
    suspenso_ate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_suspensao: Mapped[str | None] = mapped_column(String(20), nullable=True)  # manual | atraso

    emprestimos: Mapped[list["Emprestimo"]] = relationship(back_populates="usuario")


class Livro(Base):
    __tablename__ = "livros"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(300))
    autor: Mapped[str] = mapped_column(String(200))
    isbn: Mapped[str] = mapped_column(String(13), unique=True)
    ano: Mapped[int] = mapped_column(Integer)
    area_conhecimento: Mapped[str] = mapped_column(String(100), index=True)

    exemplares: Mapped[list["Exemplar"]] = relationship(back_populates="livro")


class Exemplar(Base):
    __tablename__ = "exemplares"
    __table_args__ = (
        CheckConstraint(_in("estado", ESTADOS_EXEMPLAR), name="ck_exemplar_estado"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    livro_id: Mapped[int] = mapped_column(ForeignKey("livros.id"), index=True)
    codigo_tombo: Mapped[str] = mapped_column(String(50), unique=True)
    estado: Mapped[str] = mapped_column(String(20), default="disponivel")

    livro: Mapped[Livro] = relationship(back_populates="exemplares")


class Emprestimo(Base):
    __tablename__ = "emprestimos"
    __table_args__ = (
        CheckConstraint(_in("estado", ESTADOS_EMPRESTIMO), name="ck_emprestimo_estado"),
        CheckConstraint("numero_renovacoes >= 0", name="ck_emprestimo_renov"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exemplar_id: Mapped[int] = mapped_column(ForeignKey("exemplares.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    data_retirada: Mapped[datetime] = mapped_column(DateTime)
    data_prevista: Mapped[date] = mapped_column(Date)
    data_devolucao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="ativo")
    numero_renovacoes: Mapped[int] = mapped_column(Integer, default=0)
    dias_atraso: Mapped[int] = mapped_column(Integer, default=0)

    exemplar: Mapped[Exemplar] = relationship()
    usuario: Mapped[Usuario] = relationship(back_populates="emprestimos")
    multa: Mapped["Multa | None"] = relationship(back_populates="emprestimo", uselist=False)


class Reserva(Base):
    __tablename__ = "reservas"
    __table_args__ = (
        CheckConstraint(_in("estado", ESTADOS_RESERVA), name="ck_reserva_estado"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    livro_id: Mapped[int] = mapped_column(ForeignKey("livros.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    data_reserva: Mapped[datetime] = mapped_column(DateTime)
    posicao_fila: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="aguardando")
    # Preenchidos quando a reserva passa a "disponivel".
    exemplar_id: Mapped[int | None] = mapped_column(ForeignKey("exemplares.id"), nullable=True)
    data_disponibilizacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    livro: Mapped[Livro] = relationship()
    usuario: Mapped[Usuario] = relationship()
    exemplar: Mapped[Exemplar | None] = relationship()


class Multa(Base):
    __tablename__ = "multas"
    __table_args__ = (
        CheckConstraint(_in("estado", ESTADOS_MULTA), name="ck_multa_estado"),
        CheckConstraint("valor >= 0", name="ck_multa_valor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    emprestimo_id: Mapped[int] = mapped_column(ForeignKey("emprestimos.id"), unique=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    estado: Mapped[str] = mapped_column(String(20), default="aberta")
    dias_atraso: Mapped[int] = mapped_column(Integer)
    data_geracao: Mapped[datetime] = mapped_column(DateTime)
    data_pagamento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    emprestimo: Mapped[Emprestimo] = relationship(back_populates="multa")
