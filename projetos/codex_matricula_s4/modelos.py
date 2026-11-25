from datetime import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Texto = Annotated[str, Field(min_length=1, max_length=200)]
Semestre = Annotated[str, Field(pattern=r"^[0-9]{4}\.[12]$")]
InteiroPositivo = Annotated[int, Field(strict=True, gt=0)]
Categoria = Literal["graduacao", "pos", "especial"]
SituacaoAluno = Literal["ativo", "trancado", "jubilado"]
EstadoTurma = Literal["aberta", "lotada", "cancelada", "encerrada"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Aluno(Entrada):
    nome: Texto
    matricula: Texto
    email: Annotated[str, Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]
    categoria: Categoria
    situacao: SituacaoAluno = "ativo"


class Disciplina(Entrada):
    codigo: Texto
    nome: Texto
    creditos: InteiroPositivo
    carga_horaria: InteiroPositivo
    departamento: Texto


class Horario(Entrada):
    dia: Annotated[int, Field(strict=True, ge=1, le=7)]
    inicio: time
    fim: time

    @model_validator(mode="after")
    def validar_intervalo(self):
        if self.inicio.tzinfo or self.fim.tzinfo or self.inicio >= self.fim:
            raise ValueError("Informe horas locais em um intervalo crescente")
        return self


class Turma(Entrada):
    disciplina_id: InteiroPositivo
    semestre: Semestre
    professor: Texto
    vagas: InteiroPositivo
    horario: Horario
    estado: EstadoTurma = "aberta"


class Solicitacao(Entrada):
    aluno_id: InteiroPositivo
    turma_id: InteiroPositivo


class PreRequisito(Entrada):
    exigida_id: InteiroPositivo


class Historico(Entrada):
    disciplina_id: InteiroPositivo
    semestre: Semestre
    nota: Annotated[float, Field(ge=0, le=10)] | None = None
    situacao: Literal["aprovado", "reprovado", "trancado"]
