from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.multa import Multa
from app.models.emprestimo import Emprestimo
from app.models.usuario import Usuario
from app.models.enums import EstadoMulta


def get_multas(
    db: Session,
    usuario_id: Optional[int] = None,
    estado: Optional[EstadoMulta] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Multa]:
    query = db.query(Multa).join(Emprestimo)
    if usuario_id:
        query = query.filter(Emprestimo.usuario_id == usuario_id)
    if estado:
        query = query.filter(Multa.estado == estado)
    return query.order_by(Multa.id.desc()).offset(skip).limit(limit).all()


def get_multa_by_id(db: Session, multa_id: int) -> Multa:
    multa = db.query(Multa).filter(Multa.id == multa_id).first()
    if not multa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Multa com ID {multa_id} não encontrada.",
        )
    return multa


def get_multas_por_usuario(db: Session, usuario_id: int) -> List[Multa]:
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
        .order_by(Multa.id.desc())
        .all()
    )


def pagar_multa(db: Session, multa_id: int) -> Multa:
    multa = get_multa_by_id(db, multa_id)
    if multa.estado == EstadoMulta.PAGA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multa já se encontra paga.",
        )
    if multa.estado == EstadoMulta.PERDOADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multa perdoada não requer pagamento.",
        )

    multa.estado = EstadoMulta.PAGA
    db.commit()
    db.refresh(multa)
    return multa
