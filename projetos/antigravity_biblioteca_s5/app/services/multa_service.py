from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import EstadoMulta
from app.models.emprestimo import Emprestimo
from app.models.multa import Multa
from app.models.usuario import Usuario


def listar_multas_por_usuario(db: Session, usuario_id: int) -> list[Multa]:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {usuario_id} não encontrado.",
        )

    return (
        db.query(Multa)
        .join(Emprestimo)
        .filter(Emprestimo.usuario_id == usuario_id)
        .order_by(Multa.data_geracao.desc())
        .all()
    )


def listar_todas_multas(
    db: Session,
    estado: EstadoMulta | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Multa]:
    query = db.query(Multa)
    if estado:
        query = query.filter(Multa.estado == estado)
    return query.order_by(Multa.data_geracao.desc()).offset(skip).limit(limit).all()


def obter_multa_por_id(db: Session, multa_id: int) -> Multa:
    multa = db.query(Multa).filter(Multa.id == multa_id).first()
    if not multa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Multa com ID {multa_id} não encontrada.",
        )
    return multa


def registrar_pagamento_multa(db: Session, multa_id: int, now: datetime | None = None) -> Multa:
    if now is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

    multa = obter_multa_por_id(db, multa_id)

    if multa.estado == EstadoMulta.PAGA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multa já está paga.",
        )
    if multa.estado == EstadoMulta.PERDOADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multa perdoada não requer pagamento.",
        )

    multa.estado = EstadoMulta.PAGA
    multa.data_pagamento = now
    db.commit()
    db.refresh(multa)
    return multa
