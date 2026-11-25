from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Numero = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,30}$")]
Dinheiro = Annotated[Decimal, Field(ge=0, le=Decimal("999999999999.99"), decimal_places=2)]
Positivo = Annotated[Decimal, Field(gt=0, le=Decimal("999999999999.99"), decimal_places=2)]
Categoria = Literal["comum", "premium", "empresarial"]
Situacao = Literal["ativo", "bloqueado"]
TipoConta = Literal["corrente", "poupanca"]
EstadoConta = Literal["ativa", "bloqueada", "encerrada"]
EstadoCartao = Literal["ativo", "bloqueado", "cancelado"]
Id = Annotated[int, Field(gt=0)]
Mes = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClienteDados(Entrada):
    nome: Nome
    cpf: str
    email: EmailStr
    categoria: Categoria
    situacao: Situacao = "ativo"

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, valor):
        import re

        if not re.fullmatch(r"[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}", valor):
            raise ValueError("Formato de CPF invalido")
        digitos = [int(d) for d in valor if d.isdigit()]
        if len(set(digitos)) == 1:
            raise ValueError("CPF invalido")
        for tamanho in (9, 10):
            soma = sum(d * peso for d, peso in zip(digitos, range(tamanho + 1, 1, -1)))
            if (soma * 10 % 11) % 10 != digitos[tamanho]:
                raise ValueError("CPF invalido")
        return "".join(map(str, digitos))


class ContaDados(Entrada):
    numero: Numero
    tipo: TipoConta
    limite_credito: Dinheiro = Decimal(0)
    estado: EstadoConta = "ativa"


class ContaNova(ContaDados):
    cliente_id: Id
    estado: Literal["ativa", "bloqueada"] = "ativa"


class CartaoDados(Entrada):
    numero: Numero
    limite: Dinheiro
    estado: EstadoCartao = "ativo"


class CartaoNovo(CartaoDados):
    conta_id: Id
    estado: Literal["ativo", "bloqueado"] = "ativo"


class Movimento(Entrada):
    conta_id: Id
    valor: Positivo


class Transferencia(Movimento):
    destino_id: Id


class FaturaNova(Entrada):
    mes_referencia: Mes
    vencimento: date
    valor: Positivo
    estado: Literal["aberta", "fechada"] = "fechada"
