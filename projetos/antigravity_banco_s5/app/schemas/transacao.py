from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator
from app.config import TipoTransacao, EstadoTransacao


class DepositoRequest(BaseModel):
    conta_id: int
    valor: Decimal
    descricao: Optional[str] = "Depósito em conta"

    @field_validator("valor")
    @classmethod
    def validar_valor_positivo(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("O valor do depósito deve ser maior que zero.")
        return round(v, 2)


class SaqueRequest(BaseModel):
    conta_id: int
    valor: Decimal
    descricao: Optional[str] = "Saque em conta"

    @field_validator("valor")
    @classmethod
    def validar_valor_positivo(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("O valor do saque deve ser maior que zero.")
        return round(v, 2)


class TransferenciaRequest(BaseModel):
    conta_origem_id: int
    conta_destino_id: int
    valor: Decimal
    descricao: Optional[str] = "Transferência entre contas"

    @field_validator("valor")
    @classmethod
    def validar_valor_positivo(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("O valor da transferência deve ser maior que zero.")
        return round(v, 2)


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
    transacoes: List[TransacaoResponse]
