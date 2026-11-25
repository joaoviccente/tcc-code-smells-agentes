from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import database
from .erros import ErroNegocio
from .servicos import processar_rotinas


def get_db() -> Iterator[Session]:
    db = database.SessionLocal()
    try:
        # Atualiza atrasos, suspensoes e expiracao de reservas antes de atender.
        processar_rotinas(db)
        db.commit()
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def garantir_unico(db: Session, modelo, campo: str, valor, ignorar_id: int | None = None) -> None:
    coluna = getattr(modelo, campo)
    existente = db.scalar(select(modelo).where(coluna == valor))
    if existente is not None and existente.id != ignorar_id:
        raise ErroNegocio(f"Ja existe registro com {campo} = {valor}", 409, "duplicado")
