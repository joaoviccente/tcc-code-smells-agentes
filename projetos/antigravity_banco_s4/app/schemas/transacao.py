from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from app.models.enums import TipoTransacao, EstadoTransacao


class DepositoRequest(BaseModel):
    conta_id: int = Field(..., description="ID da conta destinatária do depósito")
    valor: Decimal = Field(..., gt=0, description="Valor a depositar (deve ser maior que zero)")
    descricao: Optional[str] = Field(None, max_length=255)


class SaqueRequest(BaseModel):
    conta_id: int = Field(..., description="ID da conta para saque")
    valor: Decimal = Field(..., gt=0, description="Valor a sacar (deve ser maior que zero)")
    descricao: Optional[str] = Field(None, max_length=255)


class TransferenciaRequest(BaseModel):
    conta_origem_id: int = Field(..., description="ID da conta de origem")
    conta_destino_id: int = Field(..., description="ID da conta de destino")
    valor: Decimal = Field(..., gt=0, description="Valor a transferir (deve ser maior que zero)")
    descricao: Optional[str] = Field(None, max_length=255)


class TransacaoResponse(BaseModel):
    id: int
    conta_id: int
    conta_destino_id: Optional[int] = None
    transacao_origem_id: Optional[int] = None
    tipo: TipoTransacao
    valor: Decimal
    data: datetime
    estado: EstadoTransacao
    descricao: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExtratoResponse(BaseModel):
    conta_id: int
    numero_conta: str
    saldo_atual: Decimal
    limite_de_credito: Decimal
    saldo_disponivel: Decimal
    total_transacoes: int
    transacoes: List[TransacaoResponse]
