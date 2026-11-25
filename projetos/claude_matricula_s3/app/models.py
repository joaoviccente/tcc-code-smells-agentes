"""Modelos relacionais."""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


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


class DiaSemana(str, enum.Enum):
    SEG = "SEG"
    TER = "TER"
    QUA = "QUA"
    QUI = "QUI"
    SEX = "SEX"
    SAB = "SAB"
    DOM = "DOM"


def _enum(tipo):
    return Enum(
        tipo,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
        length=20,
    )


class Aluno(Base):
    __tablename__ = "alunos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
    matricula: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    categoria: Mapped[CategoriaAluno] = mapped_column(_enum(CategoriaAluno))
    situacao: Mapped[SituacaoAluno] = mapped_column(
        _enum(SituacaoAluno), default=SituacaoAluno.ativo
    )

    matriculas: Mapped[list["Matricula"]] = relationship(back_populates="aluno")


class Disciplina(Base):
    __tablename__ = "disciplinas"
    __table_args__ = (
        CheckConstraint("creditos > 0", name="ck_disciplina_creditos"),
        CheckConstraint("carga_horaria > 0", name="ck_disciplina_carga"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(150))
    creditos: Mapped[int] = mapped_column(Integer)
    carga_horaria: Mapped[int] = mapped_column(Integer)
    departamento: Mapped[str] = mapped_column(String(100), index=True)

    pre_requisitos: Mapped[list["PreRequisito"]] = relationship(
        foreign_keys="PreRequisito.disciplina_id",
        back_populates="disciplina",
        cascade="all, delete-orphan",
    )


class PreRequisito(Base):
    __tablename__ = "pre_requisitos"
    __table_args__ = (
        UniqueConstraint("disciplina_id", "requisito_id", name="uq_pre_requisito"),
        CheckConstraint("disciplina_id <> requisito_id", name="ck_pre_requisito_proprio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    disciplina_id: Mapped[int] = mapped_column(
        ForeignKey("disciplinas.id", ondelete="CASCADE"), index=True
    )
    requisito_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id"), index=True)

    disciplina: Mapped[Disciplina] = relationship(
        foreign_keys=[disciplina_id], back_populates="pre_requisitos"
    )
    requisito: Mapped[Disciplina] = relationship(foreign_keys=[requisito_id])


class Turma(Base):
    __tablename__ = "turmas"
    __table_args__ = (CheckConstraint("vagas > 0", name="ck_turma_vagas"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id"), index=True)
    semestre: Mapped[str] = mapped_column(String(6), index=True)
    professor: Mapped[str] = mapped_column(String(150))
    vagas: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoTurma] = mapped_column(_enum(EstadoTurma), default=EstadoTurma.aberta)

    disciplina: Mapped[Disciplina] = relationship()
    horarios: Mapped[list["HorarioTurma"]] = relationship(
        back_populates="turma", cascade="all, delete-orphan", order_by="HorarioTurma.id"
    )
    matriculas: Mapped[list["Matricula"]] = relationship(back_populates="turma")


class HorarioTurma(Base):
    __tablename__ = "horarios_turma"
    __table_args__ = (CheckConstraint("inicio < fim", name="ck_horario_intervalo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    turma_id: Mapped[int] = mapped_column(ForeignKey("turmas.id", ondelete="CASCADE"), index=True)
    dia: Mapped[DiaSemana] = mapped_column(_enum(DiaSemana))
    inicio: Mapped[str] = mapped_column(String(5))  # HH:MM
    fim: Mapped[str] = mapped_column(String(5))  # HH:MM

    turma: Mapped[Turma] = relationship(back_populates="horarios")


class Matricula(Base):
    __tablename__ = "matriculas"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("alunos.id"), index=True)
    turma_id: Mapped[int] = mapped_column(ForeignKey("turmas.id"), index=True)
    data: Mapped[datetime] = mapped_column(DateTime)  # data da solicitação
    estado: Mapped[EstadoMatricula] = mapped_column(_enum(EstadoMatricula), index=True)
    data_confirmacao: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Preenchido quando uma vaga é oferecida a quem está na lista de espera.
    prazo_confirmacao: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    data_cancelamento: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    motivo_cancelamento: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    aluno: Mapped[Aluno] = relationship(back_populates="matriculas")
    turma: Mapped[Turma] = relationship(back_populates="matriculas")

    @property
    def semestre(self) -> str:
        return self.turma.semestre

    @property
    def disciplina_id(self) -> int:
        return self.turma.disciplina_id

    @property
    def disciplina_codigo(self) -> str:
        return self.turma.disciplina.codigo


class Historico(Base):
    __tablename__ = "historicos"
    __table_args__ = (
        CheckConstraint("nota IS NULL OR (nota >= 0 AND nota <= 10)", name="ck_historico_nota"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("alunos.id"), index=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id"), index=True)
    semestre: Mapped[str] = mapped_column(String(6), index=True)
    nota: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    situacao: Mapped[SituacaoHistorico] = mapped_column(_enum(SituacaoHistorico))
    observacao: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    matricula_id: Mapped[Optional[int]] = mapped_column(ForeignKey("matriculas.id"), nullable=True)

    disciplina: Mapped[Disciplina] = relationship()

    @property
    def disciplina_codigo(self) -> str:
        return self.disciplina.codigo


class PeriodoMatricula(Base):
    """Controle do período de matrícula de cada semestre (regra 5)."""

    __tablename__ = "periodos_matricula"

    semestre: Mapped[str] = mapped_column(String(6), primary_key=True)
    encerrado: Mapped[bool] = mapped_column(Boolean, default=False)
    data_encerramento: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
