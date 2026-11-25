from collections.abc import Iterator

from sqlalchemy.orm import Session

from . import database
from .servicos import processar_expiracoes


def get_db() -> Iterator[Session]:
    db = database.SessionLocal()
    try:
        # Prazos de 48h da lista de espera sao aplicados antes de cada requisicao.
        processar_expiracoes(db)
        yield db
    finally:
        db.close()
