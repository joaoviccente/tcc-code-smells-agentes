from datetime import datetime, time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

from app.enums import (
    CategoriaAluno, DiaSemana, EstadoMatricula, EstadoTurma, SituacaoAluno, SituacaoHistorico,
)

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Departamento = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Semestre = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{4}\.[12]$")]
CodigoMatricula = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9]{4,20}$")]
CodigoDisciplina = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True,
                                                    pattern=r"^[A-Za-z0-9_-]{2,20}$")]
Id = Annotated[int, Field(ge=1)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- Aluno
class AlunoCreate(Entrada):
    nome: Texto
    matricula: CodigoMatricula
    email: EmailStr
    categoria: CategoriaAluno
    situacao: SituacaoAluno = SituacaoAluno.ATIVO


class AlunoUpdate(Entrada):
    nome: Texto | None = None
    email: EmailStr | None = None
    categoria: CategoriaAluno | None = None
    situacao: SituacaoAluno | None = None


class AlunoOut(Saida):
    id: int
    nome: str
    matricula: str
    email: str
    categoria: CategoriaAluno
    situacao: SituacaoAluno


# ----------------------------------------------------------- Disciplina
class DisciplinaCreate(Entrada):
    codigo: CodigoDisciplina
    nome: Texto
    creditos: int = Field(ge=1, le=40)
    carga_horaria: int = Field(ge=1, le=1000)
    departamento: Departamento
    pre_requisitos: list[Id] = Field(default_factory=list, description="IDs das disciplinas exigidas")


class DisciplinaUpdate(Entrada):
    nome: Texto | None = None
    creditos: int | None = Field(default=None, ge=1, le=40)
    carga_horaria: int | None = Field(default=None, ge=1, le=1000)
    departamento: Departamento | None = None


class PreRequisitoIn(Entrada):
    requisito_id: Id


class PreRequisitoOut(Saida):
    requisito_id: int


class DisciplinaOut(Saida):
    id: int
    codigo: str
    nome: str
    creditos: int
    carga_horaria: int
    departamento: str
    pre_requisitos: list[PreRequisitoOut]


# ---------------------------------------------------------------- Turma
class HorarioIn(Entrada):
    dia_semana: DiaSemana
    hora_inicio: time
    hora_fim: time

    @model_validator(mode="after")
    def _intervalo(self):
        if self.hora_inicio >= self.hora_fim:
            raise ValueError("hora_inicio deve ser anterior a hora_fim")
        return self


class HorarioOut(Saida):
    dia_semana: DiaSemana
    hora_inicio: time
    hora_fim: time


def _sem_sobreposicao(horarios):
    if not horarios:
        return horarios
    for i, a in enumerate(horarios):
        for b in horarios[i + 1:]:
            if a.dia_semana == b.dia_semana and a.hora_inicio < b.hora_fim and b.hora_inicio < a.hora_fim:
                raise ValueError("horarios da turma se sobrepoem")
    return horarios


class TurmaCreate(Entrada):
    disciplina_id: Id
    semestre: Semestre
    professor: Texto
    vagas: int = Field(ge=1, le=1000)
    horarios: list[HorarioIn] = Field(min_length=1, max_length=14)

    @field_validator("horarios")
    @classmethod
    def _horarios(cls, v):
        return _sem_sobreposicao(v)


class TurmaUpdate(Entrada):
    professor: Texto | None = None
    vagas: int | None = Field(default=None, ge=1, le=1000)
    horarios: list[HorarioIn] | None = Field(default=None, min_length=1, max_length=14)

    @field_validator("horarios")
    @classmethod
    def _horarios(cls, v):
        return _sem_sobreposicao(v)


class TurmaOut(Saida):
    id: int
    disciplina_id: int
    semestre: str
    professor: str
    vagas: int
    estado: EstadoTurma
    horarios: list[HorarioOut]
    vagas_ocupadas: int
    confirmadas: int
    tamanho_lista_espera: int


# ------------------------------------------------------------ Matricula
class MatriculaCreate(Entrada):
    aluno_id: Id
    turma_id: Id


class MatriculaOut(Saida):
    id: int
    aluno_id: int
    turma_id: int
    disciplina_id: int
    disciplina_codigo: str
    semestre: str
    data: datetime
    data_confirmacao: datetime | None
    prazo_confirmacao: datetime | None
    estado: EstadoMatricula
    observacao: str | None


class CancelamentoOut(BaseModel):
    matricula: MatriculaOut
    reprovacao_por_falta: bool


class ItemListaEspera(BaseModel):
    posicao: int
    matricula_id: int
    aluno_id: int
    aluno_nome: str
    categoria: CategoriaAluno
    prioridade: str
    data_solicitacao: datetime


class ListaEsperaOut(BaseModel):
    turma_id: int
    estado_turma: EstadoTurma
    vagas: int
    vagas_ocupadas: int
    fila: list[ItemListaEspera]


# ------------------------------------------------------------ Historico
class HistoricoCreate(Entrada):
    disciplina_id: Id
    semestre: Semestre
    nota: float | None = Field(default=None, ge=0, le=10)
    situacao: SituacaoHistorico
    observacao: Annotated[str, StringConstraints(max_length=300)] | None = None

    @model_validator(mode="after")
    def _nota(self):
        if self.situacao != SituacaoHistorico.TRANCADO and self.nota is None:
            raise ValueError("nota e obrigatoria para situacao aprovado/reprovado")
        if self.situacao == SituacaoHistorico.TRANCADO and self.nota is not None:
            raise ValueError("registro trancado nao possui nota")
        return self


class HistoricoOut(Saida):
    id: int
    aluno_id: int
    disciplina_id: int
    disciplina_codigo: str
    semestre: str
    nota: float | None
    situacao: SituacaoHistorico
    observacao: str | None


# -------------------------------------------------------- Encerramento
class EncerramentoPeriodoOut(BaseModel):
    semestre: str
    turmas_canceladas: list[int]
    turmas_mantidas: list[int]
    matriculas_canceladas: int
