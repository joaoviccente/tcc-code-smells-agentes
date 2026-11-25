from datetime import datetime, time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .enums import (
    CategoriaAluno,
    DiaSemana,
    EstadoMatricula,
    EstadoTurma,
    SituacaoAluno,
    SituacaoHistorico,
)

SEMESTRE_PATTERN = r"^\d{4}\.[12]$"

Semestre = Annotated[str, Field(pattern=SEMESTRE_PATTERN, examples=["2026.1"])]
Nome = Annotated[str, Field(min_length=2, max_length=150)]
CodigoMatricula = Annotated[str, Field(pattern=r"^[A-Za-z0-9]{4,20}$")]
CodigoDisciplina = Annotated[str, Field(pattern=r"^[A-Za-z0-9]{3,15}$")]
Departamento = Annotated[str, Field(min_length=2, max_length=100)]
Id = Annotated[int, Field(ge=1)]


class Entrada(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Parcial(Entrada):
    """Base para atualizacoes parciais (PATCH): campos enviados nao podem ser nulos."""

    @model_validator(mode="after")
    def _validar_parcial(self):
        if not self.model_fields_set:
            raise ValueError("informe ao menos um campo para atualizar")
        nulos = sorted(c for c in self.model_fields_set if getattr(self, c) is None)
        if nulos:
            raise ValueError(f"campos nao podem ser nulos: {', '.join(nulos)}")
        return self


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- Aluno
class AlunoCreate(Entrada):
    nome: Nome
    matricula: CodigoMatricula
    email: EmailStr
    categoria: CategoriaAluno
    situacao: SituacaoAluno = SituacaoAluno.ATIVO

    @field_validator("email")
    @classmethod
    def _email_minusculo(cls, v: str) -> str:
        return v.lower()


class AlunoUpdate(Parcial):
    nome: Nome | None = None
    matricula: CodigoMatricula | None = None
    email: EmailStr | None = None
    categoria: CategoriaAluno | None = None
    situacao: SituacaoAluno | None = None

    @field_validator("email")
    @classmethod
    def _email_minusculo(cls, v: str | None) -> str | None:
        return v.lower() if v else v


class AlunoOut(Saida):
    id: int
    nome: str
    matricula: str
    email: str
    categoria: CategoriaAluno
    situacao: SituacaoAluno


# ---------------------------------------------------------------- Disciplina
class DisciplinaCreate(Entrada):
    codigo: CodigoDisciplina
    nome: Nome
    creditos: int = Field(ge=1, le=28)
    carga_horaria: int = Field(ge=1, le=1000, description="Carga horaria em horas")
    departamento: Departamento

    @field_validator("codigo")
    @classmethod
    def _maiusculo(cls, v: str) -> str:
        return v.upper()


class DisciplinaUpdate(Parcial):
    codigo: CodigoDisciplina | None = None
    nome: Nome | None = None
    creditos: int | None = Field(None, ge=1, le=28)
    carga_horaria: int | None = Field(None, ge=1, le=1000)
    departamento: Departamento | None = None

    @field_validator("codigo")
    @classmethod
    def _maiusculo(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class DisciplinaOut(Saida):
    id: int
    codigo: str
    nome: str
    creditos: int
    carga_horaria: int
    departamento: str


class PreRequisitoCreate(Entrada):
    requisito_id: Id


# ---------------------------------------------------------------- Turma
class SlotHorario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dia: DiaSemana
    inicio: time
    fim: time

    @model_validator(mode="after")
    def _intervalo_valido(self):
        if self.inicio >= self.fim:
            raise ValueError("o horario de inicio deve ser anterior ao de fim")
        return self


def _validar_horario(slots: list[SlotHorario] | None) -> list[SlotHorario] | None:
    if not slots:
        return slots
    for i, a in enumerate(slots):
        for b in slots[i + 1 :]:
            if a.dia == b.dia and a.inicio < b.fim and b.inicio < a.fim:
                raise ValueError(f"horarios sobrepostos na propria turma ({a.dia.value})")
    return slots


Horario = Annotated[list[SlotHorario], Field(min_length=1, max_length=14)]


class TurmaCreate(Entrada):
    disciplina_id: Id
    semestre: Semestre
    professor: Nome
    vagas: int = Field(ge=1, le=1000)
    horario: Horario

    @field_validator("horario")
    @classmethod
    def _horario_sem_sobreposicao(cls, v):
        return _validar_horario(v)


class TurmaUpdate(Parcial):
    disciplina_id: Id | None = None
    semestre: Semestre | None = None
    professor: Nome | None = None
    vagas: int | None = Field(None, ge=1, le=1000)
    horario: Horario | None = None

    @field_validator("horario")
    @classmethod
    def _horario_sem_sobreposicao(cls, v):
        return _validar_horario(v)


class TurmaOut(Saida):
    id: int
    disciplina_id: int
    disciplina_codigo: str
    semestre: str
    professor: str
    vagas: int
    vagas_ocupadas: int
    horario: list[SlotHorario]
    estado: EstadoTurma


# ---------------------------------------------------------------- Matricula
class MatriculaCreate(Entrada):
    aluno_id: Id
    turma_id: Id


class MatriculaOut(Saida):
    id: int
    aluno_id: int
    turma_id: int
    disciplina_codigo: str
    semestre: str
    estado: EstadoMatricula
    data_solicitacao: datetime
    data_confirmacao: datetime | None
    prazo_confirmacao: datetime | None
    data_atualizacao: datetime
    posicao_fila: int | None = None


class ResultadoOperacao(BaseModel):
    matricula: MatriculaOut
    avisos: list[str] = []


class ItemFila(BaseModel):
    posicao: int
    matricula_id: int
    aluno_id: int
    aluno_nome: str
    categoria: CategoriaAluno
    prioridade: str
    data_solicitacao: datetime


class AguardandoConfirmacao(BaseModel):
    matricula_id: int
    aluno_id: int
    aluno_nome: str
    prazo_confirmacao: datetime


class ListaEsperaOut(BaseModel):
    turma_id: int
    estado: EstadoTurma
    vagas: int
    vagas_ocupadas: int
    aguardando_confirmacao: list[AguardandoConfirmacao]
    fila: list[ItemFila]


# ---------------------------------------------------------------- Historico
class HistoricoCreate(Entrada):
    aluno_id: Id
    disciplina_id: Id
    semestre: Semestre
    nota: float | None = Field(None, ge=0, le=10)
    situacao: SituacaoHistorico

    @model_validator(mode="after")
    def _nota_coerente(self):
        if self.situacao == SituacaoHistorico.TRANCADO and self.nota is not None:
            raise ValueError("registro de trancamento nao possui nota")
        if self.situacao != SituacaoHistorico.TRANCADO and self.nota is None:
            raise ValueError("nota obrigatoria para aprovado/reprovado")
        return self


class HistoricoOut(Saida):
    id: int
    aluno_id: int
    disciplina_id: int
    disciplina_codigo: str
    disciplina_nome: str
    semestre: str
    nota: float | None
    situacao: SituacaoHistorico
    por_falta: bool


class HistoricoAlunoOut(BaseModel):
    aluno_id: int
    aluno_nome: str
    resumo: dict[str, int]
    registros: list[HistoricoOut]


# ---------------------------------------------------------------- Periodo / relatorios
class EncerramentoPeriodoOut(BaseModel):
    semestre: str
    turmas_canceladas: list[int]
    turmas_mantidas: list[int]


class DisciplinaProcuradaOut(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    departamento: str
    total_solicitacoes: int
    confirmadas: int
    lista_de_espera: int


class TaxaReprovacaoOut(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    aprovados: int
    reprovados: int
    trancados: int
    taxa_reprovacao: float | None = Field(description="reprovados / (aprovados + reprovados)")


class OcupacaoTurmaOut(BaseModel):
    turma_id: int
    disciplina_codigo: str
    estado: EstadoTurma
    vagas: int
    confirmadas: int
    vagas_ocupadas: int
    lista_de_espera: int
    taxa_ocupacao: float


class OcupacaoDepartamentoOut(BaseModel):
    departamento: str
    total_turmas: int
    total_vagas: int
    total_ocupadas: int
    taxa_ocupacao: float
    turmas: list[OcupacaoTurmaOut]
