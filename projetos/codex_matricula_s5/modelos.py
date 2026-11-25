from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Semestre = Annotated[str, StringConstraints(pattern=r"^\d{4}-[12]$")]
Positivo = Annotated[int, Field(strict=True, gt=0)]
Hora = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


class Categoria(StrEnum):
    GRADUACAO = "graduacao"
    POS = "pos"
    ESPECIAL = "especial"


class SituacaoAluno(StrEnum):
    ATIVO = "ativo"
    TRANCADO = "trancado"
    JUBILADO = "jubilado"


class EstadoTurma(StrEnum):
    ABERTA = "aberta"
    LOTADA = "lotada"
    CANCELADA = "cancelada"
    ENCERRADA = "encerrada"


class SituacaoHistorico(StrEnum):
    APROVADO = "aprovado"
    REPROVADO = "reprovado"
    TRANCADO = "trancado"


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Aluno(Entrada):
    nome: Texto
    matricula: Texto
    email: EmailStr
    categoria: Categoria
    situacao: SituacaoAluno = SituacaoAluno.ATIVO


class Disciplina(Entrada):
    codigo: Texto
    nome: Texto
    creditos: Positivo
    carga_horaria: Positivo
    departamento: Texto


class Horario(Entrada):
    dia: Annotated[int, Field(strict=True, ge=1, le=7)]
    inicio: Hora
    fim: Hora

    @model_validator(mode="after")
    def validar_intervalo(self):
        if self.inicio >= self.fim:
            raise ValueError("O inicio deve anteceder o fim")
        return self


class Turma(Entrada):
    disciplina_id: Positivo
    semestre: Semestre
    professor: Texto
    vagas: Positivo
    horario: list[Horario] = Field(min_length=1)
    estado: EstadoTurma = EstadoTurma.ABERTA

    @model_validator(mode="after")
    def validar_horario(self):
        ordenado = sorted(self.horario, key=lambda h: (h.dia, h.inicio))
        if any(a.dia == b.dia and a.fim > b.inicio for a, b in zip(ordenado, ordenado[1:])):
            raise ValueError("Os horarios da turma se sobrepoem")
        return self


class Solicitacao(Entrada):
    aluno_id: Positivo
    turma_id: Positivo


class PreRequisito(Entrada):
    exigida_id: Positivo


class Historico(Entrada):
    disciplina_id: Positivo
    semestre: Semestre
    nota: Annotated[float, Field(ge=0, le=10)] | None = None
    situacao: SituacaoHistorico
