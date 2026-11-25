from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .enums import (
    CategoriaAluno,
    EstadoMatricula,
    EstadoTurma,
    SituacaoAluno,
    SituacaoHistorico,
)


def _enum(tipo):
    return SAEnum(
        tipo,
        native_enum=False,
        length=20,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
    )


class Aluno(Base):
    __tablename__ = "alunos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
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
    codigo: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(150))
    creditos: Mapped[int] = mapped_column(Integer)
    carga_horaria: Mapped[int] = mapped_column(Integer)
    departamento: Mapped[str] = mapped_column(String(100), index=True)

    turmas: Mapped[list["Turma"]] = relationship(back_populates="disciplina")


class PreRequisito(Base):
    __tablename__ = "pre_requisitos"
    __table_args__ = (
        UniqueConstraint("disciplina_id", "requisito_id", name="uq_pre_requisito"),
        CheckConstraint("disciplina_id <> requisito_id", name="ck_pre_requisito_distinto"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id"), index=True)
    requisito_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id"), index=True)

    disciplina: Mapped[Disciplina] = relationship(foreign_keys=[disciplina_id])
    requisito: Mapped[Disciplina] = relationship(foreign_keys=[requisito_id])


class Turma(Base):
    __tablename__ = "turmas"
    __table_args__ = (CheckConstraint("vagas > 0", name="ck_turma_vagas"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id"), index=True)
    semestre: Mapped[str] = mapped_column(String(6), index=True)
    professor: Mapped[str] = mapped_column(String(150))
    vagas: Mapped[int] = mapped_column(Integer)
    # Lista de {"dia": "SEG", "inicio": "08:00:00", "fim": "10:00:00"}
    horario: Mapped[list] = mapped_column(JSON)
    estado: Mapped[EstadoTurma] = mapped_column(_enum(EstadoTurma), default=EstadoTurma.ABERTA)

    disciplina: Mapped[Disciplina] = relationship(back_populates="turmas")
    matriculas: Mapped[list["Matricula"]] = relationship(back_populates="turma")

    @property
    def disciplina_codigo(self) -> str:
        return self.disciplina.codigo

    @property
    def vagas_ocupadas(self) -> int:
        return sum(
            1
            for m in self.matriculas
            if m.estado in (EstadoMatricula.SOLICITADA, EstadoMatricula.CONFIRMADA)
        )


class Matricula(Base):
    __tablename__ = "matriculas"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("alunos.id"), index=True)
    turma_id: Mapped[int] = mapped_column(ForeignKey("turmas.id"), index=True)
    data_solicitacao: Mapped[datetime] = mapped_column(DateTime)
    data_confirmacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Preenchido quando a vaga e oferecida a alguem da lista de espera (48h).
    prazo_confirmacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_atualizacao: Mapped[datetime] = mapped_column(DateTime)
    estado: Mapped[EstadoMatricula] = mapped_column(_enum(EstadoMatricula), index=True)

    aluno: Mapped[Aluno] = relationship(back_populates="matriculas")
    turma: Mapped[Turma] = relationship(back_populates="matriculas")

    # Atributo transiente (nao persistido), preenchido para respostas da API.
    posicao_fila = None

    @property
    def disciplina_codigo(self) -> str:
        return self.turma.disciplina.codigo

    @property
    def semestre(self) -> str:
        return self.turma.semestre


class Historico(Base):
    __tablename__ = "historicos"
    __table_args__ = (
        CheckConstraint("nota IS NULL OR (nota >= 0 AND nota <= 10)", name="ck_historico_nota"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("alunos.id"), index=True)
    disciplina_id: Mapped[int] = mapped_column(ForeignKey("disciplinas.id"), index=True)
    semestre: Mapped[str] = mapped_column(String(6))
    nota: Mapped[float | None] = mapped_column(Float, nullable=True)
    situacao: Mapped[SituacaoHistorico] = mapped_column(_enum(SituacaoHistorico))
    por_falta: Mapped[bool] = mapped_column(Boolean, default=False)

    aluno: Mapped[Aluno] = relationship(back_populates="historico")
    disciplina: Mapped[Disciplina] = relationship()

    @property
    def disciplina_codigo(self) -> str:
        return self.disciplina.codigo

    @property
    def disciplina_nome(self) -> str:
        return self.disciplina.nome
