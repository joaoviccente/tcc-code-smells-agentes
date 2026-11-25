"""Fonte unica de data/hora da aplicacao (permite fixar o tempo em testes)."""
from datetime import datetime

_instante_fixo: datetime | None = None


def agora() -> datetime:
    return _instante_fixo or datetime.now()


def fixar(instante: datetime | None) -> None:
    global _instante_fixo
    _instante_fixo = instante
