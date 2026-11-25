from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.emprestimo import Emprestimo
from app.models.enums import EstadoMulta
from app.models.multa import Multa
from app.models.usuario import Usuario


def list_multas_usuario(
    db: Session, usuario_id: int, estado: Optional[EstadoMulta] = None
) -> List[Multa]:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {usuario_id} não encontrado.",
        )

    query = (
        db.query(Multa)
        .join(Emprestimo, Multa.emprestimo_id == Emprestimo.id)
        .filter(Emprestimo.usuario_id == usuario_id)
    )
    if estado is not None:
        query = query.filter(Multa.estado == estado)
    return query.order_by(Multa.data_geracao.desc()).all()


def registrar_pagamento(
    db: Session, multa_id: int, data_pagamento: Optional[datetime] = None
) -> Multa:
    if data_pagamento is None:
        data_pagamento = datetime.now(timezone.utc)
    elif data_pagamento.tzinfo is None:
        data_pagamento = data_pagamento.replace(tzinfo=timezone.utc)

    multa = db.query(Multa).filter(Multa.id == multa_id).first()
    if not multa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Multa com ID {multa_id} não encontrada.",
        )

    if multa.estado == EstadoMulta.PAGA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A multa já foi paga anteriormente.",
        )

    if multa.estado == EstadoMulta.PERDOADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A multa foi perdoada e não exige pagamento.",
        )

    multa.estado = EstadoMulta.PAGA
    multa.data_pagamento = data_pagamento
    db.commit()
    db.refresh(multa)
    return multa


def get_multa(db: Session, multa_id: int) -> Multa:
    multa = db.query(Multa).filter(Multa.id == multa_id).first()
    if not multa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Multa com ID {multa_id} não encontrada.",
        )
    return multa


def list_multas(
    db: Session,
    estado: Optional[EstadoMulta] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Multa]:
    query = db.query(Multa)
    if estado is not None:
        query = query.filter(Multa.estado == estado)
    return query.order_by(Multa.data_geracao.desc()).offset(skip).limit(limit).all()
