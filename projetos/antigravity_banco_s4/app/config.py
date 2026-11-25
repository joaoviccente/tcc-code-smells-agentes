import os
from decimal import Decimal
from typing import Dict, Any


class Settings:
    PROJECT_NAME: str = "API de Gestão de Contas Correntes"
    VERSION: str = "1.0.0"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./banco.db")
    
    # Tarifa padrão cobrada em transferências quando excedida a franquia mensal
    TARIFA_TRANSFERENCIA_EXCEDENTE: Decimal = Decimal(os.getenv("TARIFA_TRANSFERENCIA_EXCEDENTE", "10.00"))


settings = Settings()


# Regras e limites por categoria de cliente
REGRAS_CATEGORIAS: Dict[str, Dict[str, Any]] = {
    "comum": {
        "limite_diario_saque": Decimal("1000.00"),
        "limite_por_transferencia": Decimal("5000.00"),
        "tarifa_mensal": Decimal("30.00"),
        "transacoes_isentas_mes": 3,
        "juros_atraso_mes": Decimal("0.08"),  # 8% ao mês
    },
    "premium": {
        "limite_diario_saque": Decimal("5000.00"),
        "limite_por_transferencia": Decimal("50000.00"),
        "tarifa_mensal": Decimal("0.00"),
        "transacoes_isentas_mes": None,  # Ilimitadas
        "juros_atraso_mes": Decimal("0.05"),  # 5% ao mês
    },
    "empresarial": {
        "limite_diario_saque": Decimal("20000.00"),
        "limite_por_transferencia": Decimal("200000.00"),
        "tarifa_mensal": Decimal("120.00"),
        "transacoes_isentas_mes": 50,
        "juros_atraso_mes": Decimal("0.03"),  # 3% ao mês
    },
}
