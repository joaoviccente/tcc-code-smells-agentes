from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import (BaseModel, ConfigDict, EmailStr, Field, StringConstraints,
                      field_validator, model_validator)

from app.models import (CategoriaAluno, EstadoMatricula, EstadoTurma,
                        SituacaoAluno, SituacaoHistorico)

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Semestre = Annotated[str, StringConstraints(pattern=r"^\d{4}\.[12]$")]
CodigoMatricula = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9]{4,20}$")]
CodigoDisciplina = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True,
                                                    pattern=r"^[A-Za-z0-9]{2,20}$")]
Hora = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class Esquema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


# ---------------------------------------------------------------- Aluno
class AlunoCriar(Esquema):
    nome: Texto
    matricula: CodigoMatricula
    email: EmailStr
    categoria: CategoriaAluno
    situacao: SituacaoAluno = SituacaoAluno.ativo


class AlunoAtualizar(Esquema):
    nome: Optional[Texto] = None
    email: Optional[EmailStr] = None
    categoria: Optional[CategoriaAluno] = None
    situacao: Optional[SituacaoAluno] = None


class AlunoSaida(Esquema):
    id: int
    nome: str
    matricula: str
    email: str
    categoria: CategoriaAluno
    situacao: SituacaoAluno


# ----------------------------------------------------------- Disciplina
class DisciplinaCriar(Esquema):
    codigo: CodigoDisciplina
    nome: Texto
    creditos: int = Field(gt=0, le=40)
    carga_horaria: int = Field(gt=0, le=1000)
    departamento: Texto


class DisciplinaAtualizar(Esquema):
    nome: Optional[Texto] = None
    creditos: Optional[int] = Field(default=None, gt=0, le=40)
    carga_horaria: Optional[int] = Field(default=None, gt=0, le=1000)
    departamento: Optional[Texto] = None


class DisciplinaSaida(Esquema):
    id: int
    codigo: str
    nome: str
    creditos: int
    carga_horaria: int
    departamento: str


class PreRequisitoCriar(Esquema):
    requisito_id: int = Field(gt=0)


# ---------------------------------------------------------------- Turma
DiaSemana = Literal["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


class Horario(Esquema):
    dia: DiaSemana
    inicio: Hora
    fim: Hora

    @model_validator(mode="after")
    def _ordem(self):
        if self.inicio >= self.fim:
            raise ValueError("'inicio' deve ser anterior a 'fim'")
        return self


def _validar_horarios(v: Optional[list[Horario]]):
    if v is None:
        return v
    for i, a in enumerate(v):
        for b in v[i + 1:]:
            if a.dia == b.dia and a.inicio < b.fim and b.inicio < a.fim:
                raise ValueError("a turma possui horarios sobrepostos entre si")
    return v


class TurmaCriar(Esquema):
    disciplina_id: int = Field(gt=0)
    semestre: Semestre
    professor: Texto
    vagas: int = Field(gt=0, le=1000)
    horario: list[Horario] = Field(min_length=1)

    _v = field_validator("horario")(_validar_horarios)


class TurmaAtualizar(Esquema):
    professor: Optional[Texto] = None
    vagas: Optional[int] = Field(default=None, gt=0, le=1000)
    horario: Optional[list[Horario]] = Field(default=None, min_length=1)
    estado: Optional[Literal["cancelada", "encerrada"]] = None

    _v = field_validator("horario")(_validar_horarios)


class TurmaSaida(Esquema):
    id: int
    disciplina_id: int
    semestre: str
    professor: str
    vagas: int
    horario: list[Horario]
    estado: EstadoTurma
    vagas_ocupadas: int = 0


# ------------------------------------------------------------ Matricula
class MatriculaCriar(Esquema):
    aluno_id: int = Field(gt=0)
    turma_id: int = Field(gt=0)


class MatriculaSaida(Esquema):
    id: int
    aluno_id: int
    turma_id: int
    data: datetime
    estado: EstadoMatricula
    data_confirmacao: Optional[datetime] = None
    prazo_confirmacao: Optional[datetime] = None
    data_encerramento: Optional[datetime] = None
    motivo_encerramento: Optional[str] = None
    posicao_lista_espera: Optional[int] = None


class CancelamentoSaida(Esquema):
    matricula: MatriculaSaida
    dentro_do_prazo: bool
    reprovacao_registrada: bool


class TrancamentoSaida(Esquema):
    matricula: MatriculaSaida
    trancamentos_no_semestre: int
    aluno_trancado: bool
    matriculas_canceladas: list[int]


class ItemListaEspera(Esquema):
    posicao: int
    matricula_id: int
    aluno_id: int
    categoria: CategoriaAluno
    prioridade: str
    data_solicitacao: datetime
    vaga_oferecida: bool
    prazo_confirmacao: Optional[datetime]


class ListaEsperaSaida(Esquema):
    turma_id: int
    vagas: int
    vagas_ocupadas: int
    fila: list[ItemListaEspera]


# ------------------------------------------------------------ Historico
class HistoricoCriar(Esquema):
    aluno_id: int = Field(gt=0)
    disciplina_id: int = Field(gt=0)
    semestre: Semestre
    nota: Optional[float] = Field(default=None, ge=0, le=10)
    situacao: SituacaoHistorico
    observacao: Optional[Annotated[str, StringConstraints(max_length=500)]] = None

    @model_validator(mode="after")
    def _nota(self):
        if self.situacao != SituacaoHistorico.trancado and self.nota is None:
            raise ValueError("'nota' e obrigatoria para aprovado/reprovado")
        if self.situacao == SituacaoHistorico.trancado and self.nota is not None:
            raise ValueError("registro de trancamento nao possui nota")
        return self


class HistoricoSaida(Esquema):
    id: int
    aluno_id: int
    disciplina_id: int
    codigo_disciplina: str
    nome_disciplina: str
    semestre: str
    nota: Optional[float]
    situacao: SituacaoHistorico
    observacao: Optional[str]
    matricula_id: Optional[int]
