"""Relogio da aplicacao (UTC, sem timezone). Permite deslocamento em testes."""

from datetime import datetime, timedelta, timezone

_deslocamento = timedelta(0)


def agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + _deslocamento


def avancar(delta: timedelta) -> None:
    global _deslocamento
    _deslocamento += delta


def reiniciar() -> None:
    global _deslocamento
    _deslocamento = timedelta(0)
