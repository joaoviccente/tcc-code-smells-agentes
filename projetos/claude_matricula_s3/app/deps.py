from datetime import datetime

from fastapi import Depends
from sqlalchemy.orm import Session

from .clock import agora
from .database import get_db
from .services.matriculas import processar_expiracoes


def obter_agora() -> datetime:
    return agora()


def db_sincronizado(
    db: Session = Depends(get_db), instante: datetime = Depends(obter_agora)
) -> Session:
    """Sessão com as ofertas vencidas da lista de espera já processadas (regra 2)."""
    if processar_expiracoes(db, instante):
        db.commit()
    return db


def paginacao(skip: int = 0, limit: int = 100) -> tuple[int, int]:
    from .errors import ErroAPI

    if skip < 0 or not (1 <= limit <= 500):
        raise ErroAPI(422, "PAGINACAO_INVALIDA", "Use skip >= 0 e 1 <= limit <= 500.")
    return skip, limit
