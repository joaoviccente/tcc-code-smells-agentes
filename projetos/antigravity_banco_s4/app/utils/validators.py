import re


def clean_cpf(cpf: str) -> str:
    """Remove caracteres não numéricos do CPF."""
    return re.sub(r"\D", "", cpf or "")


def validate_cpf(cpf: str) -> str:
    """
    Valida um CPF brasileiro.
    Retorna o CPF contendo apenas 11 dígitos se válido.
    Levanta ValueError se for inválido.
    """
    cleaned = clean_cpf(cpf)
    
    if len(cleaned) != 11:
        raise ValueError("CPF deve conter exatamente 11 dígitos numéricos.")
    
    # CPFs com todos os dígitos iguais são inválidos
    if cleaned == cleaned[0] * 11:
        raise ValueError("CPF inválido (todos os dígitos são iguais).")
    
    # Validação do primeiro dígito verificador
    soma_1 = sum(int(cleaned[i]) * (10 - i) for i in range(9))
    resto_1 = (soma_1 * 10) % 11
    digito_1 = 0 if resto_1 == 10 else resto_1
    
    if digito_1 != int(cleaned[9]):
        raise ValueError("CPF inválido (primeiro dígito verificador incompatível).")
    
    # Validação do segundo dígito verificador
    soma_2 = sum(int(cleaned[i]) * (11 - i) for i in range(10))
    resto_2 = (soma_2 * 10) % 11
    digito_2 = 0 if resto_2 == 10 else resto_2
    
    if digito_2 != int(cleaned[10]):
        raise ValueError("CPF inválido (segundo dígito verificador incompatível).")
    
    return cleaned


def format_cpf(cpf: str) -> str:
    """Formata CPF para XXX.XXX.XXX-XX."""
    cleaned = clean_cpf(cpf)
    if len(cleaned) == 11:
        return f"{cleaned[:3]}.{cleaned[3:6]}.{cleaned[6:9]}-{cleaned[9:]}"
    return cpf
