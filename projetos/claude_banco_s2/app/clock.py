"""Relogio centralizado da aplicacao. Permite fixar o 'agora' em testes."""
from datetime import datetime

_fixo: datetime | None = None


def agora() -> datetime:
    return _fixo if _fixo is not None else datetime.now()


def fixar(momento: datetime | None) -> None:
    global _fixo
    _fixo = momento
