import re
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

from app.models import (
    Categoria, EstadoMatricula, EstadoTurma, SituacaoAluno, SituacaoHistorico,
)

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Semestre = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{4}\.[12]$")]
_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- Alunos
class AlunoBase(BaseModel):
    nome: Texto
    matricula: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9]{4,30}$")]
    email: EmailStr
    categoria: Categoria


class AlunoCreate(AlunoBase):
    situacao: SituacaoAluno = SituacaoAluno.ATIVO


class AlunoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: Texto | None = None
    email: EmailStr | None = None
    categoria: Categoria | None = None
    situacao: SituacaoAluno | None = None


class AlunoOut(AlunoBase, ORM):
    id: int
    situacao: SituacaoAluno


# ---------------------------------------------------------------- Disciplinas
class DisciplinaBase(BaseModel):
    codigo: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9]{3,20}$")]
    nome: Texto
    creditos: int = Field(gt=0, le=40)
    carga_horaria: int = Field(gt=0, le=1000)
    departamento: Texto


class DisciplinaCreate(DisciplinaBase):
    pass


class DisciplinaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: Texto | None = None
    creditos: int | None = Field(default=None, gt=0, le=40)
    carga_horaria: int | None = Field(default=None, gt=0, le=1000)
    departamento: Texto | None = None


class DisciplinaOut(DisciplinaBase, ORM):
    id: int


class PreRequisitoCreate(BaseModel):
    requisito_id: int = Field(gt=0)


class PreRequisitoOut(ORM):
    id: int
    disciplina_id: int
    requisito_id: int
    requisito: DisciplinaOut


# ---------------------------------------------------------------- Turmas
class DiaSemana(str, Enum):
    SEG = "seg"
    TER = "ter"
    QUA = "qua"
    QUI = "qui"
    SEX = "sex"
    SAB = "sab"


class Horario(BaseModel):
    dia: DiaSemana
    inicio: str
    fim: str

    @field_validator("inicio", "fim")
    @classmethod
    def _hora(cls, v: str) -> str:
        if not _HORA.match(v):
            raise ValueError("hora deve estar no formato HH:MM")
        return v

    @model_validator(mode="after")
    def _ordem(self):
        if self.inicio >= self.fim:
            raise ValueError("inicio deve ser anterior ao fim")
        return self


def _validar_horarios(hs: list[Horario] | None):
    if not hs:
        return hs
    for i, a in enumerate(hs):
        for b in hs[i + 1:]:
            if a.dia == b.dia and a.inicio < b.fim and b.inicio < a.fim:
                raise ValueError("horarios da propria turma se sobrepoem")
    return hs


class TurmaCreate(BaseModel):
    disciplina_id: int = Field(gt=0)
    semestre: Semestre
    professor: Texto
    vagas: int = Field(gt=0, le=500)
    horario: list[Horario] = Field(min_length=1)

    @field_validator("horario")
    @classmethod
    def _horario(cls, v):
        return _validar_horarios(v)


class TurmaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    professor: Texto | None = None
    vagas: int | None = Field(default=None, gt=0, le=500)
    horario: list[Horario] | None = Field(default=None, min_length=1)
    estado: EstadoTurma | None = Field(
        default=None, description="Apenas 'cancelada' ou 'encerrada'; 'aberta'/'lotada' sao calculados."
    )

    @field_validator("horario")
    @classmethod
    def _horario(cls, v):
        return _validar_horarios(v)

    @field_validator("estado")
    @classmethod
    def _estado(cls, v):
        if v is not None and v not in (EstadoTurma.CANCELADA, EstadoTurma.ENCERRADA):
            raise ValueError("estado so pode ser alterado manualmente para 'cancelada' ou 'encerrada'")
        return v


class TurmaOut(ORM):
    id: int
    disciplina_id: int
    semestre: str
    professor: str
    vagas: int
    horario: list[Horario]
    estado: EstadoTurma
    vagas_ocupadas: int = 0
    vagas_disponiveis: int = 0


# ---------------------------------------------------------------- Matriculas
class MatriculaCreate(BaseModel):
    aluno_id: int = Field(gt=0)
    turma_id: int = Field(gt=0)


class MatriculaOut(ORM):
    id: int
    aluno_id: int
    turma_id: int
    data: datetime
    estado: EstadoMatricula
    data_confirmacao: datetime | None
    prazo_confirmacao: datetime | None
    data_atualizacao: datetime
    motivo: str | None
    posicao_fila: int | None = None


class CancelamentoOut(BaseModel):
    matricula: MatriculaOut
    reprovacao_por_falta: bool


class TrancamentoOut(BaseModel):
    matricula: MatriculaOut
    trancamentos_no_semestre: int
    aluno_trancado: bool


class FilaItem(BaseModel):
    posicao: int
    matricula_id: int
    aluno_id: int
    aluno_nome: str
    categoria: Categoria
    prioridade: str
    data_solicitacao: datetime
    vaga_oferecida: bool
    prazo_confirmacao: datetime | None


class FilaOut(BaseModel):
    turma_id: int
    estado_turma: EstadoTurma
    vagas: int
    vagas_ocupadas: int
    fila: list[FilaItem]


# ---------------------------------------------------------------- Historico
class HistoricoCreate(BaseModel):
    disciplina_id: int = Field(gt=0)
    semestre: Semestre
    nota: float | None = Field(default=None, ge=0, le=10)
    situacao: SituacaoHistorico
    observacao: Annotated[str, StringConstraints(max_length=255)] | None = None

    @model_validator(mode="after")
    def _coerencia(self):
        if self.situacao == SituacaoHistorico.TRANCADO and self.nota is not None:
            raise ValueError("registro trancado nao possui nota")
        if self.situacao != SituacaoHistorico.TRANCADO and self.nota is None:
            raise ValueError("nota e obrigatoria para aprovado/reprovado")
        return self


class HistoricoOut(ORM):
    id: int
    aluno_id: int
    disciplina_id: int
    disciplina_codigo: str
    disciplina_nome: str
    semestre: str
    nota: float | None
    situacao: SituacaoHistorico
    observacao: str | None


# ---------------------------------------------------------------- Encerramento do periodo
class EncerramentoPeriodoOut(BaseModel):
    semestre: str
    turmas_canceladas: list[int]
    turmas_mantidas: list[int]
    matriculas_canceladas: int
