import enum
from datetime import datetime

from sqlalchemy import (
    JSON, CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clock import agora
from app.database import Base


class Categoria(str, enum.Enum):
    GRADUACAO = "graduacao"
    POS = "pos"
    ESPECIAL = "especial"


class SituacaoAluno(str, enum.Enum):
    ATIVO = "ativo"
    TRANCADO = "trancado"
    JUBILADO = "jubilado"


class EstadoTurma(str, enum.Enum):
    ABERTA = "aberta"
    LOTADA = "lotada"
    CANCELADA = "cancelada"
    ENCERRADA = "encerrada"


class EstadoMatricula(str, enum.Enum):
    SOLICITADA = "solicitada"
    CONFIRMADA = "confirmada"
    LISTA_DE_ESPERA = "lista_de_espera"
    CANCELADA = "cancelada"
    TRANCADA = "trancada"


class SituacaoHistorico(str, enum.Enum):
    APROVADO = "aprovado"
    REPROVADO = "reprovado"
    TRANCADO = "trancado"


def _enum(e):
    return Enum(e, native_enum=False, values_callable=lambda x: [m.value for m in x], length=20)


class Aluno(Base):
    __tablename__ = "alunos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
    matricula: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    categoria: Mapped[Categoria] = mapped_column(_enum(Categoria))
    situacao: Mapped[SituacaoAluno] = mapped_column(_enum(SituacaoAluno), default=SituacaoAluno.ATIVO)

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
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id", ondelete="CASCADE"))
    requisito_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id", ondelete="RESTRICT"))

    requisito: Mapped[Disciplina] = relationship(foreign_keys=[requisito_id])


class Turma(Base):
    __tablename__ = "turmas"
    __table_args__ = (CheckConstraint("vagas > 0", name="ck_turma_vagas"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id", ondelete="RESTRICT"), index=True)
    semestre: Mapped[str] = mapped_column(String(6), index=True)
    professor: Mapped[str] = mapped_column(String(150))
    vagas: Mapped[int] = mapped_column(Integer)
    horario: Mapped[list] = mapped_column(JSON)  # [{"dia": "seg", "inicio": "08:00", "fim": "10:00"}]
    estado: Mapped[EstadoTurma] = mapped_column(_enum(EstadoTurma), default=EstadoTurma.ABERTA)

    disciplina: Mapped[Disciplina] = relationship()
    matriculas: Mapped[list["Matricula"]] = relationship(back_populates="turma")


class Matricula(Base):
    __tablename__ = "matriculas"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("alunos.id", ondelete="RESTRICT"), index=True)
    turma_id: Mapped[int] = mapped_column(ForeignKey("turmas.id", ondelete="RESTRICT"), index=True)
    data: Mapped[datetime] = mapped_column(DateTime, default=agora)  # data da solicitacao
    estado: Mapped[EstadoMatricula] = mapped_column(_enum(EstadoMatricula))
    data_confirmacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # preenchido quando uma vaga e oferecida ao primeiro da lista de espera (48h para confirmar)
    prazo_confirmacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_atualizacao: Mapped[datetime] = mapped_column(DateTime, default=agora)
    motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)

    aluno: Mapped[Aluno] = relationship(back_populates="matriculas")
    turma: Mapped[Turma] = relationship(back_populates="matriculas")


class Historico(Base):
    __tablename__ = "historicos"
    __table_args__ = (CheckConstraint("nota IS NULL OR (nota >= 0 AND nota <= 10)", name="ck_hist_nota"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("alunos.id", ondelete="CASCADE"), index=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id", ondelete="RESTRICT"), index=True)
    semestre: Mapped[str] = mapped_column(String(6))
    nota: Mapped[float | None] = mapped_column(Float, nullable=True)
    situacao: Mapped[SituacaoHistorico] = mapped_column(_enum(SituacaoHistorico))
    observacao: Mapped[str | None] = mapped_column(String(255), nullable=True)

    disciplina: Mapped[Disciplina] = relationship()
