from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Categoria = Literal["comum", "premium", "empresarial"]
Situacao = Literal["ativo", "bloqueado"]
EstadoConta = Literal["ativa", "bloqueada", "encerrada"]
EstadoCartao = Literal["ativo", "bloqueado", "cancelado"]
Dinheiro = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Valor = Annotated[Dinheiro, Field(gt=0)]
Numero = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,24}$")]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Cliente(Entrada):
    nome: str = Field(min_length=1, max_length=200)
    cpf: str
    email: EmailStr
    categoria: Categoria
    situacao: Situacao = "ativo"

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, valor: str) -> str:
        import re

        if not re.fullmatch(r"[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}", valor):
            raise ValueError("CPF invalido")
        cpf = valor.replace(".", "").replace("-", "")
        if len(set(cpf)) == 1:
            raise ValueError("CPF invalido")
        for tamanho in (9, 10):
            soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
            if (soma * 10 % 11) % 10 != int(cpf[tamanho]):
                raise ValueError("CPF invalido")
        return cpf


class ContaDados(Entrada):
    tipo: Literal["corrente", "poupanca"]
    limite_credito: Dinheiro = Decimal("0")
    estado: EstadoConta = "ativa"


class Conta(ContaDados):
    cliente_id: int = Field(gt=0)
    numero: Numero


class CartaoDados(Entrada):
    limite: Dinheiro
    estado: EstadoCartao = "ativo"


class Cartao(CartaoDados):
    conta_id: int = Field(gt=0)
    numero: Numero


class Movimento(Entrada):
    valor: Valor


class Transferencia(Movimento):
    destino_id: int = Field(gt=0)


class Fatura(Entrada):
    mes_referencia: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    vencimento: date
    valor: Valor
    estado: Literal["aberta", "fechada"] = "fechada"
