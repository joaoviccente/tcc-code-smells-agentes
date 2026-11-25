from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel
from app.config import CategoriaCliente


class ClienteMovimentacaoItem(BaseModel):
    cliente_id: int
    nome: str
    cpf: str
    categoria: CategoriaCliente
    total_movimentado: Decimal
    quantidade_transacoes: int


class RelatorioMovimentacaoResponse(BaseModel):
    data_inicio: Optional[datetime]
    data_fim: Optional[datetime]
    clientes: List[ClienteMovimentacaoItem]


class ContaSaldoNegativoItem(BaseModel):
    conta_id: int
    numero_conta: str
    cliente_id: int
    nome_cliente: str
    cpf_cliente: str
    categoria_cliente: CategoriaCliente
    saldo: Decimal
    limite_credito: Decimal
    data_saldo_negativo_desde: Optional[datetime]
    dias_negativo: int


class RelatorioSaldoNegativoResponse(BaseModel):
    total_contas_negativas: int
    contas: List[ContaSaldoNegativoItem]


class ReceitaTarifasCategoriaItem(BaseModel):
    categoria: CategoriaCliente
    total_arrecadado: Decimal
    quantidade_tarifas: int


class RelatorioReceitaTarifasResponse(BaseModel):
    total_geral: Decimal
    detalhamento: List[ReceitaTarifasCategoriaItem]


class ProcessarInadimplenciaResponse(BaseModel):
    clientes_bloqueados: int
    cartoes_bloqueados: int
    mensagem: str
