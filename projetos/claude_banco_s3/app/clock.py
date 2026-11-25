"""Fonte unica de tempo da aplicacao (facilita testes de regras temporais)."""
from datetime import datetime


def agora() -> datetime:
    return datetime.now().replace(microsecond=0)
