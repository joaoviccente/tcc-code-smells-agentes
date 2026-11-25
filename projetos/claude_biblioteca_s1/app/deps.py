from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.servicos import sincronizar


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        sincronizar(db)  # aplica eventos temporais pendentes (atrasos, multas, suspensoes, expiracoes)
        yield db
    finally:
        db.close()
