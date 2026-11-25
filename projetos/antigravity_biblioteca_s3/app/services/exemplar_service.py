from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models import Exemplar, Livro, Emprestimo, Reserva
from app.models.enums import EstadoExemplar, EstadoReserva
from app.schemas.exemplar import ExemplarCreate, ExemplarUpdate


def verificar_cancelamento_reservas_apos_baixa(db: Session, livro_id: int) -> int:
    """
    Regra 6: se o último exemplar disponível de um livro for baixado,
    todas as reservas daquele livro são canceladas.
    """
    # Contar exemplares que não estão baixados
    exemplares_nao_baixados = db.query(Exemplar).filter(
        Exemplar.livro_id == livro_id,
        Exemplar.estado != EstadoExemplar.BAIXADO
    ).count()

    canceladas_count = 0
    if exemplares_nao_baixados == 0:
        reservas_ativas = db.query(Reserva).filter(
            Reserva.livro_id == livro_id,
            Reserva.estado.in_([EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL])
        ).all()
        for r in reservas_ativas:
            r.estado = EstadoReserva.CANCELADA
            r.posicao_fila = None
            canceladas_count += 1
        db.commit()

    return canceladas_count


def create_exemplar(db: Session, exemplar_in: ExemplarCreate) -> Exemplar:
    livro = db.query(Livro).filter(Livro.id == exemplar_in.livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {exemplar_in.livro_id} não encontrado."
        )

    codigo_limpo = exemplar_in.codigo_tombo.strip()
    if db.query(Exemplar).filter(Exemplar.codigo_tombo == codigo_limpo).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Código de tombo '{codigo_limpo}' já cadastrado."
        )

    db_exemplar = Exemplar(
        livro_id=exemplar_in.livro_id,
        codigo_tombo=codigo_limpo,
        estado=exemplar_in.estado or EstadoExemplar.DISPONIVEL,
    )
    db.add(db_exemplar)
    db.commit()
    db.refresh(db_exemplar)
    return db_exemplar


def get_exemplar_by_id(db: Session, exemplar_id: int) -> Exemplar:
    exemplar = db.query(Exemplar).filter(Exemplar.id == exemplar_id).first()
    if not exemplar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exemplar com ID {exemplar_id} não encontrado."
        )
    return exemplar


def get_exemplares(
    db: Session,
    livro_id: Optional[int] = None,
    estado: Optional[EstadoExemplar] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Exemplar]:
    query = db.query(Exemplar)
    if livro_id:
        query = query.filter(Exemplar.livro_id == livro_id)
    if estado:
        query = query.filter(Exemplar.estado == estado)
    return query.offset(skip).limit(limit).all()


def update_exemplar(db: Session, exemplar_id: int, exemplar_in: ExemplarUpdate) -> Exemplar:
    exemplar = get_exemplar_by_id(db, exemplar_id)

    if exemplar_in.codigo_tombo is not None and exemplar_in.codigo_tombo.strip() != exemplar.codigo_tombo:
        codigo_novo = exemplar_in.codigo_tombo.strip()
        if db.query(Exemplar).filter(Exemplar.codigo_tombo == codigo_novo, Exemplar.id != exemplar_id).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Código de tombo '{codigo_novo}' já cadastrado."
            )
        exemplar.codigo_tombo = codigo_novo

    estado_anterior = exemplar.estado
    if exemplar_in.estado is not None:
        exemplar.estado = exemplar_in.estado

    db.commit()
    db.refresh(exemplar)

    if exemplar.estado == EstadoExemplar.BAIXADO and estado_anterior != EstadoExemplar.BAIXADO:
        verificar_cancelamento_reservas_apos_baixa(db, exemplar.livro_id)

    return exemplar


def delete_exemplar(db: Session, exemplar_id: int) -> None:
    exemplar = get_exemplar_by_id(db, exemplar_id)

    emprestimo_ativo = db.query(Emprestimo).filter(
        Emprestimo.exemplar_id == exemplar_id,
        Emprestimo.data_devolucao.is_(None)
    ).first()
    if emprestimo_ativo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir exemplar atualmente emprestado."
        )

    livro_id = exemplar.livro_id
    db.delete(exemplar)
    db.commit()

    verificar_cancelamento_reservas_apos_baixa(db, livro_id)
