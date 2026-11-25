from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel
from app.config import CategoriaCliente


class ClienteMovimentacaoResponse(BaseModel):
    cliente_id: int
    nome: str
    cpf: str
    categoria: CategoriaCliente
    total_movimentado: Decimal
    quantidade_transacoes: int


class ContaSaldoNegativoResponse(BaseModel):
    conta_id: int
    numero: str
    cliente_id: int
    cliente_nome: str
    cliente_cpf: str
    saldo: Decimal
    limite_credito: Decimal
    saldo_negativo_desde: Optional[datetime] = None
    dias_negativo: int


class ReceitaTarifasCategoriaResponse(BaseModel):
    categoria: CategoriaCliente
    quantidade_tarifas: int
    total_arrecadado: Decimal
