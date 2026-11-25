"""Fonte unica de "agora" da aplicacao (UTC, sem tzinfo, compativel com SQLite).

Centralizar o relogio permite que os testes simulem a passagem do tempo
(prazo de 48h da lista de espera, prazos de cancelamento etc.).
"""
from datetime import datetime, timezone


def agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
