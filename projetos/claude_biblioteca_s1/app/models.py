from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Categoria(StrEnum):
    ALUNO = "aluno"
    PROFESSOR = "professor"
    VISITANTE = "visitante"


class SituacaoUsuario(StrEnum):
    ATIVO = "ativo"
    SUSPENSO = "suspenso"


class EstadoExemplar(StrEnum):
    DISPONIVEL = "disponivel"
    EMPRESTADO = "emprestado"
    RESERVADO = "reservado"
    EM_REPARO = "em_reparo"
    BAIXADO = "baixado"


class EstadoEmprestimo(StrEnum):
    ATIVO = "ativo"
    DEVOLVIDO = "devolvido"
    ATRASADO = "atrasado"


class EstadoReserva(StrEnum):
    AGUARDANDO = "aguardando"
    DISPONIVEL = "disponivel"
    EXPIRADA = "expirada"
    CANCELADA = "cancelada"
    ATENDIDA = "atendida"  # estado terminal: reserva convertida em emprestimo


class EstadoMulta(StrEnum):
    ABERTA = "aberta"
    PAGA = "paga"
    PERDOADA = "perdoada"


def _enum(e):
    return Enum(e, native_enum=False, validate_strings=True, length=20,
                values_callable=lambda x: [m.value for m in x])


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    matricula: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    categoria: Mapped[Categoria] = mapped_column(_enum(Categoria))
    situacao: Mapped[SituacaoUsuario] = mapped_column(_enum(SituacaoUsuario), default=SituacaoUsuario.ATIVO)
    # Fim da suspensao automatica (regra 2). Nulo + suspenso = suspensao manual por tempo indeterminado.
    suspenso_ate: Mapped[date | None] = mapped_column(Date, nullable=True)

    emprestimos: Mapped[list["Emprestimo"]] = relationship(back_populates="usuario")
    reservas: Mapped[list["Reserva"]] = relationship(back_populates="usuario")


class Livro(Base):
    __tablename__ = "livros"
    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(255))
    autor: Mapped[str] = mapped_column(String(255))
    isbn: Mapped[str] = mapped_column(String(13), unique=True, index=True)
    ano: Mapped[int] = mapped_column(Integer)
    area: Mapped[str] = mapped_column(String(100), index=True)

    exemplares: Mapped[list["Exemplar"]] = relationship(back_populates="livro")


class Exemplar(Base):
    __tablename__ = "exemplares"
    id: Mapped[int] = mapped_column(primary_key=True)
    livro_id: Mapped[int] = mapped_column(ForeignKey("livros.id"), index=True)
    codigo_tombo: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    estado: Mapped[EstadoExemplar] = mapped_column(_enum(EstadoExemplar), default=EstadoExemplar.DISPONIVEL)

    livro: Mapped[Livro] = relationship(back_populates="exemplares")
    emprestimos: Mapped[list["Emprestimo"]] = relationship(back_populates="exemplar")


class Emprestimo(Base):
    __tablename__ = "emprestimos"
    id: Mapped[int] = mapped_column(primary_key=True)
    exemplar_id: Mapped[int] = mapped_column(ForeignKey("exemplares.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    data_retirada: Mapped[date] = mapped_column(Date)
    data_prevista: Mapped[date] = mapped_column(Date)
    data_devolucao: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[EstadoEmprestimo] = mapped_column(_enum(EstadoEmprestimo), default=EstadoEmprestimo.ATIVO)
    renovacoes: Mapped[int] = mapped_column(Integer, default=0)

    exemplar: Mapped[Exemplar] = relationship(back_populates="emprestimos")
    usuario: Mapped[Usuario] = relationship(back_populates="emprestimos")
    multa: Mapped["Multa | None"] = relationship(back_populates="emprestimo", uselist=False)

    @property
    def livro_id(self) -> int:
        return self.exemplar.livro_id


class Reserva(Base):
    __tablename__ = "reservas"
    id: Mapped[int] = mapped_column(primary_key=True)
    livro_id: Mapped[int] = mapped_column(ForeignKey("livros.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    data: Mapped[datetime] = mapped_column(DateTime)
    posicao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[EstadoReserva] = mapped_column(_enum(EstadoReserva), default=EstadoReserva.AGUARDANDO)
    # Preenchidos quando a reserva passa a "disponivel": exemplar separado e prazo de 48h para retirada.
    exemplar_id: Mapped[int | None] = mapped_column(ForeignKey("exemplares.id"), nullable=True)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    livro: Mapped[Livro] = relationship()
    usuario: Mapped[Usuario] = relationship(back_populates="reservas")
    exemplar: Mapped[Exemplar | None] = relationship()


class Multa(Base):
    __tablename__ = "multas"
    id: Mapped[int] = mapped_column(primary_key=True)
    emprestimo_id: Mapped[int] = mapped_column(ForeignKey("emprestimos.id"), unique=True)
    valor_centavos: Mapped[int] = mapped_column(Integer)
    dias_atraso: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoMulta] = mapped_column(_enum(EstadoMulta), default=EstadoMulta.ABERTA)
    data_pagamento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    emprestimo: Mapped[Emprestimo] = relationship(back_populates="multa")

    @property
    def usuario_id(self) -> int:
        return self.emprestimo.usuario_id
