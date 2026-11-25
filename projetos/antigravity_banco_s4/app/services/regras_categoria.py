from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from app.config import REGRAS_CATEGORIAS
from app.models.enums import CategoriaCliente


class RegrasCategoriaService:
    @staticmethod
    def get_regras(categoria: CategoriaCliente) -> dict:
        chave = categoria.value if isinstance(categoria, CategoriaCliente) else str(categoria).lower()
        if chave not in REGRAS_CATEGORIAS:
            chave = "comum"
        return REGRAS_CATEGORIAS[chave]

    @classmethod
    def get_limite_diario_saque(cls, categoria: CategoriaCliente) -> Decimal:
        return cls.get_regras(categoria)["limite_diario_saque"]

    @classmethod
    def get_limite_por_transferencia(cls, categoria: CategoriaCliente) -> Decimal:
        return cls.get_regras(categoria)["limite_por_transferencia"]

    @classmethod
    def get_tarifa_mensal(cls, categoria: CategoriaCliente) -> Decimal:
        return cls.get_regras(categoria)["tarifa_mensal"]

    @classmethod
    def get_transacoes_isentas_mes(cls, categoria: CategoriaCliente) -> Optional[int]:
        return cls.get_regras(categoria)["transacoes_isentas_mes"]

    @classmethod
    def get_taxa_juros_atraso(cls, categoria: CategoriaCliente) -> Decimal:
        return cls.get_regras(categoria)["juros_atraso_mes"]

    @classmethod
    def calcular_juros_fatura(cls, valor: Decimal, categoria: CategoriaCliente, dias_atraso: int) -> Decimal:
        """
        Calcula juros proporcionais aos dias de atraso baseado na taxa mensal da categoria.
        Regra:
        Comum: 8% ao mês (0.08)
        Premium: 5% ao mês (0.05)
        Empresarial: 3% ao mês (0.03)
        Juros = valor * taxa_mensal * (dias_atraso / 30)
        """
        if dias_atraso <= 0 or valor <= Decimal("0.00"):
            return Decimal("0.00")
        
        taxa_mensal = cls.get_taxa_juros_atraso(categoria)
        # Juros pro-rata diário (dias_atraso / 30)
        fator = (taxa_mensal / Decimal("30")) * Decimal(dias_atraso)
        juros = valor * fator
        return juros.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
