"""Relogio da aplicacao. Centralizado para permitir simulacao de datas em testes."""
from datetime import datetime

_fixo: datetime | None = None


def agora() -> datetime:
    return _fixo if _fixo is not None else datetime.now().replace(microsecond=0)


def fixar(momento: datetime | None) -> None:
    global _fixo
    _fixo = momento
