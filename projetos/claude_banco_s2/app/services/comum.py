from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.errors import NaoEncontrado
from app.models import Conta, arredondar
from app.regras import DIAS_SALDO_NEGATIVO_BLOQUEIO


def obter(db: Session, modelo, id_: int, nome: str):
    obj = db.get(modelo, id_)
    if obj is None:
        raise NaoEncontrado(f"{nome} {id_} nao encontrado(a)")
    return obj


def competencia_de(momento: datetime) -> str:
    return f"{momento.year:04d}-{momento.month:02d}"


def pode_debitar(conta: Conta, valor: Decimal) -> bool:
    """Regra 2: o saldo pode ficar negativo ate o limite de credito da conta."""
    return conta.saldo - valor >= -conta.limite_credito


def movimentar_saldo(conta: Conta, delta: Decimal, agora: datetime) -> None:
    """Altera o saldo e mantem o marco de inicio do saldo negativo (regra 6)."""
    conta.saldo = arredondar(conta.saldo + delta)
    if conta.saldo < 0:
        if conta.negativo_desde is None:
            conta.negativo_desde = agora
    else:
        conta.negativo_desde = None


def negativo_prolongado(conta: Conta, agora: datetime) -> bool:
    """Regra 6: saldo negativo por mais de 30 dias."""
    return (
        conta.saldo < 0
        and conta.negativo_desde is not None
        and agora - conta.negativo_desde > timedelta(days=DIAS_SALDO_NEGATIVO_BLOQUEIO)
    )
