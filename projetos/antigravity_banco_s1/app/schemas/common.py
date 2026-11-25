import re
from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema


def validar_cpf(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("CPF deve ser uma string")
    
    # Remove caracteres não numéricos
    cpf = re.sub(r"\D", "", v)
    if len(cpf) != 11:
        raise ValueError("CPF deve conter exatamente 11 dígitos")
    
    # Rejeita CPFs com todos os dígitos iguais (ex.: 111.111.111-11)
    if len(set(cpf)) == 1:
        raise ValueError("CPF inválido: todos os dígitos são iguais")
    
    # Validação do primeiro dígito verificador
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    digito_1 = 0 if resto == 10 or resto == 11 else resto
    if int(cpf[9]) != digito_1:
        raise ValueError("Dígito verificador do CPF inválido")
    
    # Validação do segundo dígito verificador
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    digito_2 = 0 if resto == 10 or resto == 11 else resto
    if int(cpf[10]) != digito_2:
        raise ValueError("Dígito verificador do CPF inválido")
    
    return cpf


class CPF(str):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: type, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            validar_cpf,
            core_schema.str_schema(),
        )
