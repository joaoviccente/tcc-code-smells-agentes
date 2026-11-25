from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from app.models.enums import CategoriaCliente, SituacaoCliente, EstadoConta


class ClienteMovimentacaoItem(BaseModel):
    cliente_id: int
    nome: str
    cpf: str
    categoria: CategoriaCliente
    situacao: SituacaoCliente
    total_movimentado: Decimal
    quantidade_transacoes: int


class RelatorioMaiorMovimentacaoResponse(BaseModel):
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
    categoria_cliente: CategoriaCliente
    saldo: Decimal
    limite_de_credito: Decimal
    data_saldo_negativo_inicio: Optional[datetime] = None
    dias_negativo: int
    estado: EstadoConta


class RelatorioContasNegativasResponse(BaseModel):
    total_contas_negativas: int
    valor_total_negativo: Decimal
    contas: List[ContaSaldoNegativoItem]


class ReceitaCategoriaItem(BaseModel):
    categoria: CategoriaCliente
    quantidade_tarifas: int
    valor_total: Decimal


class RelatorioReceitaTarifasResponse(BaseModel):
    receita_total: Decimal
    total_tarifas_cobradas: int
    receita_por_categoria: List[ReceitaCategoriaItem]
