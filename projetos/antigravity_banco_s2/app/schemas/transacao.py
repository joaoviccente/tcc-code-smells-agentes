from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator
from app.config import TipoTransacao, EstadoTransacao


class DepositoCreate(BaseModel):
    conta_id: int
    valor: Decimal
    data: Optional[datetime] = None
    descricao: Optional[str] = None

    @field_validator("valor")
    @classmethod
    def validar_valor(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("Valor do depósito deve ser maior que zero.")
        return v


class SaqueCreate(BaseModel):
    conta_id: int
    valor: Decimal
    data: Optional[datetime] = None
    descricao: Optional[str] = None

    @field_validator("valor")
    @classmethod
    def validar_valor(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("Valor do saque deve ser maior que zero.")
        return v


class TransferenciaCreate(BaseModel):
    conta_id: int
    conta_destino_id: int
    valor: Decimal
    data: Optional[datetime] = None
    descricao: Optional[str] = None

    @field_validator("valor")
    @classmethod
    def validar_valor(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0.00"):
            raise ValueError("Valor da transferência deve ser maior que zero.")
        return v

    @field_validator("conta_destino_id")
    @classmethod
    def validar_contas_diferentes(cls, v: int, info) -> int:
        if "conta_id" in info.data and v == info.data["conta_id"]:
            raise ValueError("Conta de destino não pode ser a mesma conta de origem.")
        return v


class EstornoCreate(BaseModel):
    motivo: Optional[str] = None


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
    saldo_atual: Decimal
    limite_credito: Decimal
    transacoes: List[TransacaoResponse]
