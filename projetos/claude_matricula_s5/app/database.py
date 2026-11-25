import os
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


engine: Engine | None = None
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def configurar(url: str) -> Engine:
    """(Re)configura o engine. Qualquer banco suportado pelo SQLAlchemy pode ser usado."""
    global engine
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    SessionLocal.configure(bind=engine)
    return engine


@event.listens_for(Engine, "connect")
def _habilitar_fk_sqlite(dbapi_conn, _record):
    if isinstance(dbapi_conn, sqlite3.Connection):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def criar_tabelas() -> None:
    from . import models  # noqa: F401  (registra os modelos no metadata)

    Base.metadata.create_all(engine)


configurar(os.getenv("DATABASE_URL", "sqlite:///./matriculas.db"))
