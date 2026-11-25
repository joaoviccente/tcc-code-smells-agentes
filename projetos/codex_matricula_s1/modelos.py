from datetime import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Semestre = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-[12]$")]
InteiroPositivo = Annotated[int, Field(gt=0, le=2**63 - 1)]
Id = InteiroPositivo


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Aluno(Entrada):
    nome: Texto
    matricula: Texto
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
    categoria: Literal["graduacao", "pos", "especial"]
    situacao: Literal["ativo", "trancado", "jubilado"] = "ativo"


class Disciplina(Entrada):
    codigo: Texto
    nome: Texto
    creditos: InteiroPositivo
    carga_horaria: InteiroPositivo
    departamento: Texto


class Horario(Entrada):
    dia: Literal["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
    inicio: time
    fim: time

    @model_validator(mode="after")
    def validar_intervalo(self):
        if self.inicio.tzinfo or self.fim.tzinfo or self.inicio >= self.fim:
            raise ValueError("Informe horários locais com início anterior ao fim")
        return self


class Turma(Entrada):
    disciplina_id: Id
    semestre: Semestre
    professor: Texto
    vagas: InteiroPositivo
    horario: Annotated[list[Horario], Field(min_length=1)]
    estado: Literal["aberta", "lotada", "cancelada", "encerrada"] = "aberta"


class Solicitacao(Entrada):
    aluno_id: Id
    turma_id: Id


class PreRequisito(Entrada):
    disciplina_exigida_id: Id


class Historico(Entrada):
    disciplina_id: Id
    semestre: Semestre
    nota: Annotated[float, Field(ge=0, le=10)] | None = None
    situacao: Literal["aprovado", "reprovado", "trancado"]
