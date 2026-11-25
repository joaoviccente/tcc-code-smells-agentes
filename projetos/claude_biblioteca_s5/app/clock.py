"""Relogio da aplicacao.

Toda leitura de "agora" passa por aqui para que os testes possam simular a
passagem do tempo (atrasos, expiracao de reservas, fim de suspensao).
"""
from datetime import datetime, timedelta

_deslocamento = timedelta(0)
_fixo: datetime | None = None


def agora() -> datetime:
    if _fixo is not None:
        return _fixo
    return datetime.now().replace(microsecond=0) + _deslocamento


def fixar(momento: datetime | None) -> None:
    """Fixa o relogio num instante (None volta ao relogio real)."""
    global _fixo
    _fixo = momento


def avancar(**kwargs) -> None:
    """Avanca o relogio (ex.: avancar(days=10))."""
    global _fixo, _deslocamento
    if _fixo is not None:
        _fixo = _fixo + timedelta(**kwargs)
    else:
        _deslocamento += timedelta(**kwargs)


def resetar() -> None:
    global _fixo, _deslocamento
    _fixo = None
    _deslocamento = timedelta(0)
