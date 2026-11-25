from collections.abc import Iterator

from fastapi import Query
from sqlalchemy.orm import Session

from . import database
from .servicos import processar_pendencias


def get_db() -> Iterator[Session]:
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


class Paginacao:
    def __init__(self, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
        self.skip = skip
        self.limit = limit

    def aplicar(self, consulta):
        return consulta.offset(self.skip).limit(self.limit)
