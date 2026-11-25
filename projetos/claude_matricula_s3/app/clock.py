"""Relógio da aplicação. Todas as datas são armazenadas em UTC (naive).

Exposto como dependência para que possa ser substituído em testes.
"""
from datetime import datetime, timezone


def agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
