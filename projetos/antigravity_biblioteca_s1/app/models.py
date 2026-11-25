import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    Text,
)
from sqlalchemy.orm import relationship
from app.database import Base


class CategoriaUsuario(str, enum.Enum):
    aluno = "aluno"
    professor = "professor"
    visitante = "visitante"


class SituacaoUsuario(str, enum.Enum):
    ativo = "ativo"
    suspenso = "suspenso"


class EstadoExemplar(str, enum.Enum):
    disponivel = "disponivel"
    emprestado = "emprestado"
    reservado = "reservado"
    em_reparo = "em_reparo"
    baixado = "baixado"


class EstadoEmprestimo(str, enum.Enum):
    ativo = "ativo"
    devolvido = "devolvido"
    atrasado = "atrasado"


class EstadoReserva(str, enum.Enum):
    aguardando = "aguardando"
    disponivel = "disponivel"
    expirada = "expirada"
    cancelada = "cancelada"
    concluida = "concluida"


class EstadoMulta(str, enum.Enum):
    aberta = "aberta"
    paga = "paga"
    perdoada = "perdoada"


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nome = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    matricula = Column(String(50), unique=True, index=True, nullable=False)
    categoria = Column(Enum(CategoriaUsuario), nullable=False)
    situacao = Column(Enum(SituacaoUsuario), default=SituacaoUsuario.ativo, nullable=False)
    data_fim_suspensao = Column(DateTime, nullable=True)

    emprestimos = relationship("Emprestimo", back_populates="usuario")
    reservas = relationship("Reserva", back_populates="usuario")


class Livro(Base):
    __tablename__ = "livros"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    titulo = Column(String(255), nullable=False)
    autor = Column(String(255), nullable=False)
    isbn = Column(String(50), unique=True, index=True, nullable=False)
    ano = Column(Integer, nullable=False)
    area_conhecimento = Column(String(100), nullable=False, index=True)

    exemplares = relationship("Exemplar", back_populates="livro", cascade="all, delete-orphan")
    reservas = relationship("Reserva", back_populates="livro", cascade="all, delete-orphan")


class Exemplar(Base):
    __tablename__ = "exemplares"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    livro_id = Column(Integer, ForeignKey("livros.id"), nullable=False)
    codigo_tombo = Column(String(50), unique=True, index=True, nullable=False)
    estado = Column(Enum(EstadoExemplar), default=EstadoExemplar.disponivel, nullable=False)

    livro = relationship("Livro", back_populates="exemplares")
    emprestimos = relationship("Emprestimo", back_populates="exemplar")
    reservas = relationship("Reserva", back_populates="exemplar")


class Emprestimo(Base):
    __tablename__ = "emprestimos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exemplar_id = Column(Integer, ForeignKey("exemplares.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    data_retirada = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    data_prevista = Column(DateTime, nullable=False)
    data_devolucao = Column(DateTime, nullable=True)
    estado = Column(Enum(EstadoEmprestimo), default=EstadoEmprestimo.ativo, nullable=False)
    numero_renovacoes = Column(Integer, default=0, nullable=False)

    exemplar = relationship("Exemplar", back_populates="emprestimos")
    usuario = relationship("Usuario", back_populates="emprestimos")
    multa = relationship("Multa", back_populates="emprestimo", uselist=False, cascade="all, delete-orphan")


class Reserva(Base):
    __tablename__ = "reservas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    livro_id = Column(Integer, ForeignKey("livros.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    exemplar_id = Column(Integer, ForeignKey("exemplares.id"), nullable=True)
    data = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    posicao_fila = Column(Integer, nullable=True)
    estado = Column(Enum(EstadoReserva), default=EstadoReserva.aguardando, nullable=False)
    data_limite_retirada = Column(DateTime, nullable=True)

    livro = relationship("Livro", back_populates="reservas")
    usuario = relationship("Usuario", back_populates="reservas")
    exemplar = relationship("Exemplar", back_populates="reservas")


class Multa(Base):
    __tablename__ = "multas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    emprestimo_id = Column(Integer, ForeignKey("emprestimos.id"), nullable=False, unique=True)
    valor = Column(Numeric(10, 2), nullable=False)
    estado = Column(Enum(EstadoMulta), default=EstadoMulta.aberta, nullable=False)
    data_geracao = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    data_pagamento = Column(DateTime, nullable=True)

    emprestimo = relationship("Emprestimo", back_populates="multa")
