from datetime import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Positivo = Annotated[int, Field(strict=True, gt=0)]
Semestre = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}\.[12]$")]
Categoria = Literal["graduacao", "pos", "especial"]
SituacaoAluno = Literal["ativo", "trancado", "jubilado"]
EstadoTurma = Literal["aberta", "lotada", "cancelada", "encerrada"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Aluno(Entrada):
    nome: Texto
    matricula: Texto
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=254,
                                            pattern=r"^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$")]
    categoria: Categoria
    situacao: SituacaoAluno = "ativo"


class Disciplina(Entrada):
    codigo: Texto
    nome: Texto
    creditos: Positivo
    carga_horaria: Positivo
    departamento: Texto


class Horario(Entrada):
    dia_semana: Annotated[int, Field(strict=True, ge=1, le=7)]
    inicio: time
    fim: time

    @model_validator(mode="after")
    def validar_intervalo(self):
        if self.inicio.tzinfo or self.fim.tzinfo or self.fim <= self.inicio:
            raise ValueError("Informe horarios locais com inicio anterior ao fim.")
        return self


class Turma(Entrada):
    disciplina_id: Positivo
    semestre: Semestre
    professor: Texto
    vagas: Positivo
    horario: Horario
    estado: EstadoTurma = "aberta"


class Solicitacao(Entrada):
    aluno_id: Positivo
    turma_id: Positivo


class PreRequisito(Entrada):
    exigida_id: Positivo


class Historico(Entrada):
    disciplina_id: Positivo
    semestre: Semestre
    nota: Annotated[float, Field(ge=0, le=10)] | None = None
    situacao: Literal["aprovado", "reprovado", "trancado"]
