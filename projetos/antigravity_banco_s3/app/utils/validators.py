import re

def clean_cpf(cpf: str) -> str:
    """Remove pontuações do CPF, deixando apenas os dígitos."""
    return re.sub(r"\D", "", cpf)

def validate_cpf(cpf: str) -> bool:
    """Valida um CPF brasileiro de acordo com o cálculo dos dígitos verificadores."""
    digits = clean_cpf(cpf)
    
    if len(digits) != 11:
        return False
        
    # Rejeita CPFs com todos os dígitos iguais (ex: 111.111.111-11)
    if digits == digits[0] * 11:
        return False
        
    # Calcula primeiro dígito verificador
    soma_1 = sum(int(digits[i]) * (10 - i) for i in range(9))
    resto_1 = (soma_1 * 10) % 11
    d1 = 0 if resto_1 == 10 else resto_1
    
    if d1 != int(digits[9]):
        return False
        
    # Calcula segundo dígito verificador
    soma_2 = sum(int(digits[i]) * (11 - i) for i in range(10))
    resto_2 = (soma_2 * 10) % 11
    d2 = 0 if resto_2 == 10 else resto_2
    
    return d2 == int(digits[10])

def format_cpf(cpf: str) -> str:
    """Formata os 11 dígitos no padrão 000.000.000-00."""
    d = clean_cpf(cpf)
    if len(d) != 11:
        return cpf
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
