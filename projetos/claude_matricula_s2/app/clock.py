"""Fonte unica de tempo da aplicacao (UTC, sem timezone para compatibilidade com SQLite).

Os testes substituem `agora` para simular a passagem do tempo (prazos de 48h, 7/15/30 dias).
"""
from datetime import datetime, timezone


def agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
