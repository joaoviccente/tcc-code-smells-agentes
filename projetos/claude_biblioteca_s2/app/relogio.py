"""Fonte unica de "agora" da aplicacao (permite controlar o tempo em testes)."""
from datetime import datetime

_instante_fixo: datetime | None = None


def agora() -> datetime:
    return _instante_fixo if _instante_fixo is not None else datetime.now().replace(microsecond=0)


def fixar(instante: datetime | None) -> None:
    global _instante_fixo
    _instante_fixo = instante
