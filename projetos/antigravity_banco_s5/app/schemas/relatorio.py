from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.config import CategoriaCliente


class ClienteMovimentacaoItem(BaseModel):
    cliente_id: int
    nome: str
    cpf: str
    categoria: CategoriaCliente
    total_movimentado: Decimal
    total_transacoes: int

    model_config = ConfigDict(from_attributes=True)


class ContaSaldoNegativoItem(BaseModel):
    conta_id: int
    numero: str
    cliente_id: int
    cliente_nome: str
    cliente_cpf: str
    categoria: CategoriaCliente
    saldo: Decimal
    limite_credito: Decimal
    dias_negativo: int
    data_saldo_negativo_inicio: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ReceitaTarifasCategoriaItem(BaseModel):
    categoria: CategoriaCliente
    total_receita: Decimal
    quantidade_tarifas: int

    model_config = ConfigDict(from_attributes=True)
