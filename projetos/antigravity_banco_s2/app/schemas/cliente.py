import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from app.config import CategoriaCliente, SituacaoCliente


def validar_cpf(cpf: str) -> str:
    # Remove pontuações
    numeros = re.sub(r"\D", "", cpf)
    if len(numeros) != 11:
        raise ValueError("CPF deve conter exatamente 11 dígitos.")
    
    # Rejeita CPFs com todos os dígitos iguais
    if numeros == numeros[0] * 11:
        raise ValueError("CPF inválido (todos os dígitos iguais).")

    # Primeiro dígito verificador
    soma = sum(int(numeros[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    d1 = 0 if resto == 10 else resto

    if d1 != int(numeros[9]):
        raise ValueError("CPF inválido (primeiro dígito verificador).")

    # Segundo dígito verificador
    soma = sum(int(numeros[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    d2 = 0 if resto == 10 else resto

    if d2 != int(numeros[10]):
        raise ValueError("CPF inválido (segundo dígito verificador).")

    return numeros


class ClienteBase(BaseModel):
    nome: str
    cpf: str
    email: EmailStr
    categoria: CategoriaCliente = CategoriaCliente.COMUM
    situacao: SituacaoCliente = SituacaoCliente.ATIVO

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Nome deve ter pelo menos 2 caracteres.")
        return v

    @field_validator("cpf")
    @classmethod
    def validar_cpf_field(cls, v: str) -> str:
        return validar_cpf(v)


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    categoria: Optional[CategoriaCliente] = None
    situacao: Optional[SituacaoCliente] = None

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if len(v) < 2:
                raise ValueError("Nome deve ter pelo menos 2 caracteres.")
        return v


class ClienteResponse(ClienteBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
