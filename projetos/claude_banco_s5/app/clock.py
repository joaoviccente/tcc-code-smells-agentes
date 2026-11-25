"""Relogio central da aplicacao (substituivel em testes)."""
from datetime import datetime


def agora() -> datetime:
    return datetime.now()
