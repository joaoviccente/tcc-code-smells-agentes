from datetime import datetime
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models import Multa, Emprestimo, Usuario
from app.models.enums import EstadoMulta
from app.services.usuario_service import verificar_e_atualizar_situacao
from app.utils import get_utcnow


def get_multas_por_usuario(db: Session, usuario_id: int) -> List[Multa]:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {usuario_id} não encontrado."
        )

    return db.query(Multa).join(Emprestimo).filter(
        Emprestimo.usuario_id == usuario_id
    ).order_by(Multa.data_geracao.desc()).all()


def get_multa_by_id(db: Session, multa_id: int) -> Multa:
    multa = db.query(Multa).filter(Multa.id == multa_id).first()
    if not multa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Multa com ID {multa_id} não encontrada."
        )
    return multa


def get_multas(
    db: Session,
    estado: Optional[EstadoMulta] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Multa]:
    query = db.query(Multa)
    if estado:
        query = query.filter(Multa.estado == estado)
    return query.order_by(Multa.data_geracao.desc()).offset(skip).limit(limit).all()


def registrar_pagamento_multa(db: Session, multa_id: int) -> Multa:
    multa = get_multa_by_id(db, multa_id)

    if multa.estado == EstadoMulta.PAGA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta multa já foi paga anteriormente."
        )

    if multa.estado == EstadoMulta.PERDOADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta multa foi perdoada e não requer pagamento."
        )

    multa.estado = EstadoMulta.PAGA
    multa.data_pagamento = get_utcnow()

    usuario = multa.emprestimo.usuario
    db.commit()
    db.refresh(multa)

    verificar_e_atualizar_situacao(db, usuario)

    return multa
