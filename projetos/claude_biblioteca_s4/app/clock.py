"""Fonte unica de "agora" da aplicacao.

Centralizar o relogio permite que os testes simulem a passagem do tempo
(atrasos, expiracao de reservas, fim de suspensoes) sem esperar dias reais.
"""
from datetime import datetime
from typing import Callable

_provider: Callable[[], datetime] = datetime.now


def agora() -> datetime:
    return _provider().replace(microsecond=0)


def definir_relogio(provider: Callable[[], datetime] | None) -> None:
    global _provider
    _provider = provider or datetime.now
