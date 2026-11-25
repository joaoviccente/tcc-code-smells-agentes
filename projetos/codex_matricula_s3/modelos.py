from datetime import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Semestre = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-[12]$")]
Positivo = Annotated[int, Field(gt=0, strict=True)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Aluno(Entrada):
    nome: Texto
    matricula: Texto
    email: EmailStr
    categoria: Literal["graduacao", "pos", "especial"]
    situacao: Literal["ativo", "trancado", "jubilado"] = "ativo"


class Disciplina(Entrada):
    codigo: Texto
    nome: Texto
    creditos: Positivo
    carga_horaria: Positivo
    departamento: Texto


class Horario(Entrada):
    dia: Annotated[int, Field(ge=1, le=7, strict=True)]
    inicio: time
    fim: time

    @model_validator(mode="after")
    def validar_intervalo(self):
        if self.inicio.tzinfo or self.fim.tzinfo or self.inicio >= self.fim:
            raise ValueError("Informe horas locais com início anterior ao fim.")
        return self


class Turma(Entrada):
    disciplina_id: Positivo
    semestre: Semestre
    professor: Texto
    vagas: Positivo
    horario: Annotated[list[Horario], Field(min_length=1)]
    estado: Literal["aberta", "lotada", "cancelada", "encerrada"] = "aberta"


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
