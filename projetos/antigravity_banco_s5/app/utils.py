from datetime import datetime, timezone


def utc_now() -> datetime:
    """Retorna datetime UTC atual ingênuo (naive) para compatibilidade perfeita com SQLite e SQLAlchemy."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
