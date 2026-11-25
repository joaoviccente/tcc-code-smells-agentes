"""Valores monetarios exatos: Decimal na aplicacao, centavos (inteiro) no banco."""
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import BigInteger
from sqlalchemy.types import TypeDecorator

CENTAVO = Decimal("0.01")


def arredondar(valor) -> Decimal:
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class Money(TypeDecorator):
    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return int((arredondar(value) * 100).to_integral_value())

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (Decimal(value) / 100).quantize(CENTAVO)
