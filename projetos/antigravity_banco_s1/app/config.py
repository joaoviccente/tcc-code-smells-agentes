from decimal import Decimal
import os
from pydantic import BaseModel


class Settings(BaseModel):
    APP_NAME: str = "Banco S1 - API de Gestão de Contas Correntes"
    APP_VERSION: str = "1.0.0"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./banco.db")
    
    # Tarifa padrão quando franquia de transferências é excedida
    TARIFA_TRANSFERENCIA_PADRAO: Decimal = Decimal("10.00")


# Parâmetros e regras por categoria de cliente
CATEGORY_RULES = {
    "comum": {
        "limite_diario_saque": Decimal("1000.00"),
        "limite_por_transferencia": Decimal("5000.00"),
        "tarifa_mensal": Decimal("30.00"),
        "transacoes_isentas_mes": 3,
        "taxa_juros_atraso_mensal": Decimal("0.08"),  # 8% ao mês
    },
    "premium": {
        "limite_diario_saque": Decimal("5000.00"),
        "limite_por_transferencia": Decimal("50000.00"),
        "tarifa_mensal": Decimal("0.00"),
        "transacoes_isentas_mes": 999_999_999,  # Ilimitadas
        "taxa_juros_atraso_mensal": Decimal("0.05"),  # 5% ao mês
    },
    "empresarial": {
        "limite_diario_saque": Decimal("20000.00"),
        "limite_por_transferencia": Decimal("200000.00"),
        "tarifa_mensal": Decimal("120.00"),
        "transacoes_isentas_mes": 50,
        "taxa_juros_atraso_mensal": Decimal("0.03"),  # 3% ao mês
    },
}

settings = Settings()
