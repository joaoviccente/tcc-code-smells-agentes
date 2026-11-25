from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import database
from app.erros import ErroNegocio
from app.servicos import processar_pendencias


def get_db() -> Iterator[Session]:
    db = database.SessionLocal()
    try:
        # Regras dependentes do tempo (atrasos, multas, suspensoes, expiracao de reservas)
        processar_pendencias(db)
        db.commit()
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def garantir_unico(db: Session, modelo, campo: str, valor, id_atual: int | None = None) -> None:
    """Lanca 409 se ja existir outro registro com o mesmo valor no campo unico."""
    coluna = getattr(modelo, campo)
    existente = db.scalars(select(modelo).where(coluna == valor)).first()
    if existente is not None and existente.id != id_atual:
        raise ErroNegocio(f"Ja existe {modelo.__name__.lower()} com {campo} '{valor}'")
