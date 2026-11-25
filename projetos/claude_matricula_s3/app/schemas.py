"""Esquemas de entrada/saída (validação com Pydantic)."""
from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

from .models import (
    CategoriaAluno,
    DiaSemana,
    EstadoMatricula,
    EstadoTurma,
    SituacaoAluno,
    SituacaoHistorico,
)

SEMESTRE_REGEX = r"^\d{4}\.[12]$"
HORA_REGEX = r"^([01]\d|2[0-3]):[0-5]\d$"
MATRICULA_REGEX = r"^[A-Za-z0-9]{4,20}$"

Semestre = Annotated[str, Field(pattern=SEMESTRE_REGEX, examples=["2026.1"])]
Nome = Annotated[str, Field(min_length=2, max_length=150)]
CodigoDisciplina = Annotated[str, Field(pattern=r"^[A-Za-z0-9]{3,10}$", examples=["MAT101"])]


def _iso_utc(d: datetime) -> str:
    return d.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


DataUTC = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]


class Entrada(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Atualizacao(Entrada):
    """Atualização parcial: campos omitidos não mudam; null explícito não é aceito."""

    @model_validator(mode="after")
    def _sem_nulos(self):
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para atualizar.")
        nulos = sorted(k for k in self.model_fields_set if getattr(self, k) is None)
        if nulos:
            raise ValueError(f"Campos não podem ser nulos: {', '.join(nulos)}")
        return self


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- Aluno
class AlunoCreate(Entrada):
    nome: Nome
    matricula: str = Field(pattern=MATRICULA_REGEX, examples=["2026001234"])
    email: EmailStr
    categoria: CategoriaAluno
    situacao: SituacaoAluno = SituacaoAluno.ativo


class AlunoUpdate(Atualizacao):
    nome: Optional[Nome] = None
    matricula: Optional[str] = Field(default=None, pattern=MATRICULA_REGEX)
    email: Optional[EmailStr] = None
    categoria: Optional[CategoriaAluno] = None
    situacao: Optional[SituacaoAluno] = None


class AlunoOut(Saida):
    id: int
    nome: str
    matricula: str
    email: str
    categoria: CategoriaAluno
    situacao: SituacaoAluno


# ----------------------------------------------------------- Disciplina
def _upper(v: Optional[str]) -> Optional[str]:
    return v.upper() if v else v


class DisciplinaCreate(Entrada):
    codigo: CodigoDisciplina
    nome: Nome
    creditos: int = Field(ge=1, le=28)
    carga_horaria: int = Field(ge=1, le=1000, description="Carga horária em horas")
    departamento: str = Field(min_length=2, max_length=100)

    @field_validator("codigo")
    @classmethod
    def _codigo_maiusculo(cls, v):
        return _upper(v)


class DisciplinaUpdate(Atualizacao):
    codigo: Optional[CodigoDisciplina] = None
    nome: Optional[Nome] = None
    creditos: Optional[int] = Field(default=None, ge=1, le=28)
    carga_horaria: Optional[int] = Field(default=None, ge=1, le=1000)
    departamento: Optional[str] = Field(default=None, min_length=2, max_length=100)

    @field_validator("codigo")
    @classmethod
    def _codigo_maiusculo(cls, v):
        return _upper(v)


class DisciplinaResumo(Saida):
    id: int
    codigo: str
    nome: str


class DisciplinaOut(Saida):
    id: int
    codigo: str
    nome: str
    creditos: int
    carga_horaria: int
    departamento: str
    pre_requisitos: list[DisciplinaResumo] = []


class PreRequisitoCreate(Entrada):
    requisito_id: int = Field(gt=0, description="Disciplina exigida como pré-requisito")


# ---------------------------------------------------------------- Turma
class HorarioIn(Entrada):
    dia: DiaSemana
    inicio: str = Field(pattern=HORA_REGEX, examples=["08:00"])
    fim: str = Field(pattern=HORA_REGEX, examples=["10:00"])

    @model_validator(mode="after")
    def _intervalo(self):
        if self.inicio >= self.fim:
            raise ValueError("O horário de início deve ser anterior ao de fim.")
        return self


class HorarioOut(Saida):
    dia: DiaSemana
    inicio: str
    fim: str


def _validar_horarios(horarios: Optional[list[HorarioIn]]):
    if not horarios:
        return horarios
    for i, a in enumerate(horarios):
        for b in horarios[i + 1:]:
            if a.dia == b.dia and a.inicio < b.fim and b.inicio < a.fim:
                raise ValueError("Os horários da turma se sobrepõem entre si.")
    return horarios


class TurmaCreate(Entrada):
    disciplina_id: int = Field(gt=0)
    semestre: Semestre
    professor: Nome
    vagas: int = Field(ge=1, le=1000)
    horarios: list[HorarioIn] = Field(min_length=1, max_length=14)

    @field_validator("horarios")
    @classmethod
    def _horarios(cls, v):
        return _validar_horarios(v)


class TurmaUpdate(Atualizacao):
    professor: Optional[Nome] = None
    vagas: Optional[int] = Field(default=None, ge=1, le=1000)
    horarios: Optional[list[HorarioIn]] = Field(default=None, min_length=1, max_length=14)

    @field_validator("horarios")
    @classmethod
    def _horarios(cls, v):
        return _validar_horarios(v)


class TurmaOut(BaseModel):
    id: int
    disciplina: DisciplinaResumo
    semestre: str
    professor: str
    vagas: int
    estado: EstadoTurma
    horarios: list[HorarioOut]
    matriculas_confirmadas: int
    vagas_ocupadas: int
    vagas_disponiveis: int
    tamanho_lista_espera: int


# ------------------------------------------------------------ Matrícula
class MatriculaCreate(Entrada):
    aluno_id: int = Field(gt=0)
    turma_id: int = Field(gt=0)


class MatriculaOut(Saida):
    id: int
    aluno_id: int
    turma_id: int
    disciplina_id: int
    disciplina_codigo: str
    semestre: str
    estado: EstadoMatricula
    data: DataUTC
    data_confirmacao: Optional[DataUTC] = None
    prazo_confirmacao: Optional[DataUTC] = None
    data_cancelamento: Optional[DataUTC] = None
    motivo_cancelamento: Optional[str] = None
    posicao_lista_espera: Optional[int] = None


class OperacaoMatriculaOut(BaseModel):
    matricula: MatriculaOut
    mensagem: str
    reprovacao_por_falta_registrada: bool = False
    aluno_trancado: bool = False
    matriculas_canceladas: list[int] = []


class ItemListaEspera(BaseModel):
    posicao: int
    matricula_id: int
    aluno_id: int
    aluno_nome: str
    categoria: CategoriaAluno
    prioridade: str
    data: DataUTC
    vaga_ofertada: bool
    prazo_confirmacao: Optional[DataUTC] = None


class ListaEsperaOut(BaseModel):
    turma_id: int
    estado_turma: EstadoTurma
    vagas: int
    vagas_ocupadas: int
    fila: list[ItemListaEspera]


class EncerramentoPeriodoOut(BaseModel):
    semestre: str
    turmas_canceladas: list[int]
    turmas_mantidas: list[int]
    matriculas_canceladas: int


# ------------------------------------------------------------ Histórico
class HistoricoCreate(Entrada):
    disciplina_id: int = Field(gt=0)
    semestre: Semestre
    nota: Optional[float] = Field(default=None, ge=0, le=10)
    situacao: SituacaoHistorico
    observacao: Optional[str] = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _nota_coerente(self):
        if self.situacao == SituacaoHistorico.trancado and self.nota is not None:
            raise ValueError("Registro de trancamento não possui nota.")
        if self.situacao != SituacaoHistorico.trancado and self.nota is None:
            raise ValueError("Nota é obrigatória para aprovado/reprovado.")
        return self


class HistoricoOut(Saida):
    id: int
    aluno_id: int
    disciplina_id: int
    disciplina_codigo: str
    semestre: str
    nota: Optional[float]
    situacao: SituacaoHistorico
    observacao: Optional[str]
    matricula_id: Optional[int]
