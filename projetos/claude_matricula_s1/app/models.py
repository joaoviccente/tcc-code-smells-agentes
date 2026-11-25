from datetime import datetime, time

from sqlalchemy import (
    CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer, String, Time, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clock import agora
from app.database import Base
from app.enums import (
    CategoriaAluno, DiaSemana, EstadoMatricula, EstadoTurma, SituacaoAluno, SituacaoHistorico,
)


def _enum(e):
    return Enum(e, native_enum=False, values_callable=lambda cls: [m.value for m in cls], length=20,
                validate_strings=True)


class Aluno(Base):
    __tablename__ = "alunos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    matricula: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    categoria: Mapped[CategoriaAluno] = mapped_column(_enum(CategoriaAluno))
    situacao: Mapped[SituacaoAluno] = mapped_column(_enum(SituacaoAluno), default=SituacaoAluno.ATIVO)

    matriculas: Mapped[list["Matricula"]] = relationship(back_populates="aluno")
    historico: Mapped[list["Historico"]] = relationship(back_populates="aluno")


class Disciplina(Base):
    __tablename__ = "disciplinas"
    __table_args__ = (
        CheckConstraint("creditos > 0", name="ck_disciplina_creditos"),
        CheckConstraint("carga_horaria > 0", name="ck_disciplina_carga"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(200))
    creditos: Mapped[int] = mapped_column(Integer)
    carga_horaria: Mapped[int] = mapped_column(Integer)
    departamento: Mapped[str] = mapped_column(String(100), index=True)

    turmas: Mapped[list["Turma"]] = relationship(back_populates="disciplina")
    pre_requisitos: Mapped[list["PreRequisito"]] = relationship(
        foreign_keys="PreRequisito.disciplina_id", back_populates="disciplina", cascade="all, delete-orphan"
    )


class PreRequisito(Base):
    """Liga uma disciplina (disciplina_id) a outra disciplina exigida (requisito_id)."""
    __tablename__ = "pre_requisitos"
    __table_args__ = (
        UniqueConstraint("disciplina_id", "requisito_id", name="uq_pre_requisito"),
        CheckConstraint("disciplina_id <> requisito_id", name="ck_pre_requisito_proprio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id", ondelete="CASCADE"))
    requisito_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id", ondelete="RESTRICT"))

    disciplina: Mapped[Disciplina] = relationship(foreign_keys=[disciplina_id], back_populates="pre_requisitos")
    requisito: Mapped[Disciplina] = relationship(foreign_keys=[requisito_id])


class Turma(Base):
    __tablename__ = "turmas"
    __table_args__ = (CheckConstraint("vagas > 0", name="ck_turma_vagas"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id", ondelete="RESTRICT"), index=True)
    semestre: Mapped[str] = mapped_column(String(6), index=True)
    professor: Mapped[str] = mapped_column(String(200))
    vagas: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoTurma] = mapped_column(_enum(EstadoTurma), default=EstadoTurma.ABERTA)

    disciplina: Mapped[Disciplina] = relationship(back_populates="turmas")
    horarios: Mapped[list["HorarioTurma"]] = relationship(
        back_populates="turma", cascade="all, delete-orphan", order_by="HorarioTurma.id"
    )
    matriculas: Mapped[list["Matricula"]] = relationship(back_populates="turma")

    @property
    def vagas_ocupadas(self) -> int:
        """Vagas ocupadas: matriculas solicitadas (inclui vaga reservada a quem saiu da fila) + confirmadas."""
        return sum(1 for m in self.matriculas
                   if m.estado in (EstadoMatricula.SOLICITADA, EstadoMatricula.CONFIRMADA))

    @property
    def confirmadas(self) -> int:
        return sum(1 for m in self.matriculas if m.estado == EstadoMatricula.CONFIRMADA)

    @property
    def tamanho_lista_espera(self) -> int:
        return sum(1 for m in self.matriculas if m.estado == EstadoMatricula.LISTA_DE_ESPERA)


class HorarioTurma(Base):
    """Um encontro semanal da turma (ex.: SEG 08:00-10:00)."""
    __tablename__ = "horarios_turma"

    id: Mapped[int] = mapped_column(primary_key=True)
    turma_id: Mapped[int] = mapped_column(ForeignKey("turmas.id", ondelete="CASCADE"), index=True)
    dia_semana: Mapped[DiaSemana] = mapped_column(_enum(DiaSemana))
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)

    turma: Mapped[Turma] = relationship(back_populates="horarios")

    def conflita(self, outro: "HorarioTurma") -> bool:
        return (self.dia_semana == outro.dia_semana
                and self.hora_inicio < outro.hora_fim and outro.hora_inicio < self.hora_fim)


class Matricula(Base):
    __tablename__ = "matriculas"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("alunos.id", ondelete="RESTRICT"), index=True)
    turma_id: Mapped[int] = mapped_column(ForeignKey("turmas.id", ondelete="RESTRICT"), index=True)
    data: Mapped[datetime] = mapped_column(DateTime, default=agora)  # data da solicitacao
    data_confirmacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prazo_confirmacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    estado: Mapped[EstadoMatricula] = mapped_column(_enum(EstadoMatricula), index=True)
    observacao: Mapped[str | None] = mapped_column(String(300), nullable=True)

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
    __table_args__ = (CheckConstraint("nota IS NULL OR (nota >= 0 AND nota <= 10)", name="ck_historico_nota"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("alunos.id", ondelete="RESTRICT"), index=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id", ondelete="RESTRICT"), index=True)
    semestre: Mapped[str] = mapped_column(String(6))
    nota: Mapped[float | None] = mapped_column(Float, nullable=True)
    situacao: Mapped[SituacaoHistorico] = mapped_column(_enum(SituacaoHistorico))
    observacao: Mapped[str | None] = mapped_column(String(300), nullable=True)
    matricula_id: Mapped[int | None] = mapped_column(ForeignKey("matriculas.id", ondelete="SET NULL"),
                                                     nullable=True)

    aluno: Mapped[Aluno] = relationship(back_populates="historico")
    disciplina: Mapped[Disciplina] = relationship()

    @property
    def disciplina_codigo(self) -> str:
        return self.disciplina.codigo
