from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel

from app.models.cliente import CategoriaCliente


class ClienteMovimentacaoItem(BaseModel):
    cliente_id: int
    nome: str
    cpf: str
    categoria: CategoriaCliente
    total_movimentado: Decimal
    quantidade_transacoes: int


class RelatorioMovimentacaoResponse(BaseModel):
    data_inicio: Optional[datetime] = None
    data_fim: Optional[datetime] = None
    total_clientes_listados: int
    clientes: List[ClienteMovimentacaoItem]


class ContaSaldoNegativoItem(BaseModel):
    conta_id: int
    numero: str
    cliente_id: int
    cliente_nome: str
    cliente_cpf: str
    categoria: CategoriaCliente
    saldo: Decimal
    limite_credito: Decimal
    data_saldo_negativo: Optional[datetime]
    dias_negativo: int


class RelatorioContasSaldoNegativoResponse(BaseModel):
    total_contas_negativas: int
    contas: List[ContaSaldoNegativoItem]


class CategoriaReceitaItem(BaseModel):
    categoria: CategoriaCliente
    total_arrecadado: Decimal
    quantidade_tarifas_cobradas: int
    quantidade_tarifas_isentas: int
    tarifas_por_tipo: Dict[str, Decimal]


class RelatorioReceitaTarifasResponse(BaseModel):
    total_geral: Decimal
    categorias: List[CategoriaReceitaItem]
