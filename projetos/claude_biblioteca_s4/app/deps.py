from collections.abc import Iterator

from sqlalchemy.orm import Session

from . import database
from .servicos import processar_pendencias


def get_db() -> Iterator[Session]:
    """Abre a sessao e, antes de atender a requisicao, aplica as regras temporais."""
    db = database.SessionLocal()
    try:
        processar_pendencias(db)
        db.commit()
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
