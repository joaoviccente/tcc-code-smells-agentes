from datetime import datetime, timezone


def get_utcnow() -> datetime:
    """Retorna datetime UTC atual naive, compatível com colunas DateTime do SQLAlchemy e SQLite."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
