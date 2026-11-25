from decimal import Decimal
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.transacao import EstadoTransacao, TipoTransacao


class DepositoCreate(BaseModel):
    conta_id: int = Field(..., description="ID da conta destinatária do depósito")
    valor: Decimal = Field(..., gt=0, description="Valor do depósito")
    descricao: Optional[str] = Field(None, max_length=255)


class SaqueCreate(BaseModel):
    conta_id: int = Field(..., description="ID da conta de origem do saque")
    valor: Decimal = Field(..., gt=0, description="Valor do saque")
    descricao: Optional[str] = Field(None, max_length=255)


class TransferenciaCreate(BaseModel):
    conta_origem_id: int = Field(..., description="ID da conta de origem")
    conta_destino_id: int = Field(..., description="ID da conta de destino")
    valor: Decimal = Field(..., gt=0, description="Valor da transferência")
    descricao: Optional[str] = Field(None, max_length=255)


class TransacaoResponse(BaseModel):
    id: int
    conta_id: int
    conta_destino_id: Optional[int] = None
    tipo: TipoTransacao
    valor: Decimal
    data: datetime
    estado: EstadoTransacao
    transacao_origem_id: Optional[int] = None
    descricao: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExtratoResponse(BaseModel):
    conta_id: int
    numero_conta: str
    cliente_nome: str
    saldo_atual: Decimal
    limite_credito: Decimal
    saldo_disponivel: Decimal
    total_transacoes: int
    transacoes: List[TransacaoResponse]
