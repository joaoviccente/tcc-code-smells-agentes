import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (JSON, CheckConstraint, DateTime, Enum, Float,
                        ForeignKey, Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import clock
from app.database import Base


class CategoriaAluno(str, enum.Enum):
    graduacao = "graduacao"
    pos = "pos"
    especial = "especial"


class SituacaoAluno(str, enum.Enum):
    ativo = "ativo"
    trancado = "trancado"
    jubilado = "jubilado"


class EstadoTurma(str, enum.Enum):
    aberta = "aberta"
    lotada = "lotada"
    cancelada = "cancelada"
    encerrada = "encerrada"


class EstadoMatricula(str, enum.Enum):
    solicitada = "solicitada"
    confirmada = "confirmada"
    lista_de_espera = "lista_de_espera"
    cancelada = "cancelada"
    trancada = "trancada"


class SituacaoHistorico(str, enum.Enum):
    aprovado = "aprovado"
    reprovado = "reprovado"
    trancado = "trancado"


def _enum(e):
    return Enum(e, native_enum=False, validate_strings=True, length=20)


class Aluno(Base):
    __tablename__ = "alunos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
    matricula: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    categoria: Mapped[CategoriaAluno] = mapped_column(_enum(CategoriaAluno))
    situacao: Mapped[SituacaoAluno] = mapped_column(
        _enum(SituacaoAluno), default=SituacaoAluno.ativo)

    matriculas: Mapped[list["Matricula"]] = relationship(back_populates="aluno")


class Disciplina(Base):
    __tablename__ = "disciplinas"
    __table_args__ = (
        CheckConstraint("creditos > 0", name="ck_disc_creditos"),
        CheckConstraint("carga_horaria > 0", name="ck_disc_ch"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(150))
    creditos: Mapped[int] = mapped_column(Integer)
    carga_horaria: Mapped[int] = mapped_column(Integer)
    departamento: Mapped[str] = mapped_column(String(100), index=True)


class PreRequisito(Base):
    __tablename__ = "pre_requisitos"
    __table_args__ = (
        UniqueConstraint("disciplina_id", "requisito_id", name="uq_prereq"),
        CheckConstraint("disciplina_id <> requisito_id", name="ck_prereq_self"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    disciplina_id: Mapped[int] = mapped_column(
        ForeignKey("disciplinas.id", ondelete="CASCADE"), index=True)
    requisito_id: Mapped[int] = mapped_column(
        ForeignKey("disciplinas.id", ondelete="CASCADE"))

    requisito: Mapped[Disciplina] = relationship(foreign_keys=[requisito_id])


class Turma(Base):
    __tablename__ = "turmas"
    __table_args__ = (CheckConstraint("vagas > 0", name="ck_turma_vagas"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id"), index=True)
    semestre: Mapped[str] = mapped_column(String(6), index=True)
    professor: Mapped[str] = mapped_column(String(150))
    vagas: Mapped[int] = mapped_column(Integer)
    # lista de {"dia": "seg", "inicio": "08:00", "fim": "10:00"}
    horario: Mapped[list] = mapped_column(JSON)
    estado: Mapped[EstadoTurma] = mapped_column(
        _enum(EstadoTurma), default=EstadoTurma.aberta)

    disciplina: Mapped[Disciplina] = relationship()
    matriculas: Mapped[list["Matricula"]] = relationship(back_populates="turma")


class Matricula(Base):
    __tablename__ = "matriculas"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("alunos.id"), index=True)
    turma_id: Mapped[int] = mapped_column(ForeignKey("turmas.id"), index=True)
    data: Mapped[datetime] = mapped_column(DateTime, default=clock.agora)
    estado: Mapped[EstadoMatricula] = mapped_column(_enum(EstadoMatricula))
    data_confirmacao: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # preenchido quando uma vaga e oferecida a quem esta na lista de espera
    prazo_confirmacao: Mapped[Optional[datetime]] = mapped_column(DateTime)
    data_encerramento: Mapped[Optional[datetime]] = mapped_column(DateTime)
    motivo_encerramento: Mapped[Optional[str]] = mapped_column(String(200))

    aluno: Mapped[Aluno] = relationship(back_populates="matriculas")
    turma: Mapped[Turma] = relationship(back_populates="matriculas")


class Historico(Base):
    __tablename__ = "historicos"
    __table_args__ = (
        CheckConstraint("nota IS NULL OR (nota >= 0 AND nota <= 10)", name="ck_hist_nota"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("alunos.id"), index=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id"), index=True)
    semestre: Mapped[str] = mapped_column(String(6))
    nota: Mapped[Optional[float]] = mapped_column(Float)
    situacao: Mapped[SituacaoHistorico] = mapped_column(_enum(SituacaoHistorico))
    observacao: Mapped[Optional[str]] = mapped_column(Text)
    matricula_id: Mapped[Optional[int]] = mapped_column(ForeignKey("matriculas.id"))

    disciplina: Mapped[Disciplina] = relationship()
