import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
from app.config import CategoriaCliente, SituacaoCliente


def validar_cpf(cpf: str) -> str:
    # Remove caracteres não numéricos
    clean_cpf = re.sub(r"\D", "", cpf)
    if len(clean_cpf) != 11:
        raise ValueError("O CPF deve conter exatamente 11 dígitos numéricos.")

    # Verifica sequências repetidas
    if clean_cpf == clean_cpf[0] * 11:
        raise ValueError("CPF inválido (dígitos repetidos).")

    # Primeiro dígito verificador
    soma = sum(int(clean_cpf[i]) * (10 - i) for i in range(9))
    d1 = (soma * 10) % 11
    if d1 == 10:
        d1 = 0
    if int(clean_cpf[9]) != d1:
        raise ValueError("CPF inválido (primeiro dígito verificador não confere).")

    # Segundo dígito verificador
    soma = sum(int(clean_cpf[i]) * (11 - i) for i in range(10))
    d2 = (soma * 10) % 11
    if d2 == 10:
        d2 = 0
    if int(clean_cpf[10]) != d2:
        raise ValueError("CPF inválido (segundo dígito verificador não confere).")

    return f"{clean_cpf[:3]}.{clean_cpf[3:6]}.{clean_cpf[6:9]}-{clean_cpf[9:]}"


class ClienteBase(BaseModel):
    nome: str
    email: EmailStr
    categoria: CategoriaCliente = CategoriaCliente.COMUM
    situacao: SituacaoCliente = SituacaoCliente.ATIVO


class ClienteCreate(ClienteBase):
    cpf: str

    @field_validator("cpf")
    @classmethod
    def validar_cpf_field(cls, v: str) -> str:
        return validar_cpf(v)

    @field_validator("nome")
    @classmethod
    def validar_nome_field(cls, v: str) -> str:
        if not v or len(v.strip()) < 2:
            raise ValueError("O nome deve conter pelo menos 2 caracteres.")
        return v.strip()


class ClienteUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    categoria: Optional[CategoriaCliente] = None
    situacao: Optional[SituacaoCliente] = None

    @field_validator("nome")
    @classmethod
    def validar_nome_field(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v.strip()) < 2:
            raise ValueError("O nome deve conter pelo menos 2 caracteres.")
        return v.strip() if v else None


class ClienteResponse(ClienteBase):
    id: int
    cpf: str
    data_criacao: datetime

    model_config = ConfigDict(from_attributes=True)
