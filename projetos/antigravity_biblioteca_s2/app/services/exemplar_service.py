from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.emprestimo import Emprestimo
from app.models.enums import EstadoEmprestimo, EstadoExemplar, EstadoReserva
from app.models.exemplar import Exemplar
from app.models.livro import Livro
from app.models.reserva import Reserva
from app.schemas.exemplar import ExemplarCreate, ExemplarUpdate


def verificar_cancelamento_reservas_por_baixa(db: Session, livro_id: int) -> None:
    """Regra 6: se o último exemplar disponível de um livro for baixado,

    todas as reservas daquele livro são canceladas.
    """
    exemplares_ativos = (
        db.query(Exemplar)
        .filter(
            Exemplar.livro_id == livro_id,
            Exemplar.estado != EstadoExemplar.BAIXADO,
        )
        .count()
    )
    if exemplares_ativos == 0:
        reservas_ativas = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == livro_id,
                Reserva.estado.in_([EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL]),
            )
            .all()
        )
        for res in reservas_ativas:
            res.estado = EstadoReserva.CANCELADA
            res.posicao_fila = 0


def create_exemplar(db: Session, exemplar_in: ExemplarCreate) -> Exemplar:
    livro = db.query(Livro).filter(Livro.id == exemplar_in.livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {exemplar_in.livro_id} não encontrado.",
        )

    if db.query(Exemplar).filter(Exemplar.codigo_tombo == exemplar_in.codigo_tombo).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um exemplar cadastrado com este código de tombo.",
        )

    exemplar = Exemplar(
        livro_id=exemplar_in.livro_id,
        codigo_tombo=exemplar_in.codigo_tombo,
        estado=exemplar_in.estado or EstadoExemplar.DISPONIVEL,
    )
    db.add(exemplar)
    db.commit()
    db.refresh(exemplar)
    return exemplar


def get_exemplar(db: Session, exemplar_id: int) -> Exemplar:
    exemplar = db.query(Exemplar).filter(Exemplar.id == exemplar_id).first()
    if not exemplar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exemplar com ID {exemplar_id} não encontrado.",
        )
    return exemplar


def list_exemplares(
    db: Session,
    livro_id: Optional[int] = None,
    estado: Optional[EstadoExemplar] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Exemplar]:
    query = db.query(Exemplar)
    if livro_id is not None:
        query = query.filter(Exemplar.livro_id == livro_id)
    if estado is not None:
        query = query.filter(Exemplar.estado == estado)
    return query.offset(skip).limit(limit).all()


def update_exemplar(db: Session, exemplar_id: int, exemplar_in: ExemplarUpdate) -> Exemplar:
    exemplar = db.query(Exemplar).filter(Exemplar.id == exemplar_id).first()
    if not exemplar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exemplar com ID {exemplar_id} não encontrado.",
        )

    if exemplar_in.codigo_tombo and exemplar_in.codigo_tombo != exemplar.codigo_tombo:
        if db.query(Exemplar).filter(Exemplar.codigo_tombo == exemplar_in.codigo_tombo).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um exemplar cadastrado com este código de tombo.",
            )
        exemplar.codigo_tombo = exemplar_in.codigo_tombo

    if exemplar_in.estado is not None:
        estado_antigo = exemplar.estado
        exemplar.estado = exemplar_in.estado
        db.flush()

        # Se mudou para BAIXADO, verificar se é o último exemplar disponível
        if exemplar_in.estado == EstadoExemplar.BAIXADO and estado_antigo != EstadoExemplar.BAIXADO:
            verificar_cancelamento_reservas_por_baixa(db, exemplar.livro_id)

    db.commit()
    db.refresh(exemplar)
    return exemplar


def delete_exemplar(db: Session, exemplar_id: int) -> None:
    exemplar = db.query(Exemplar).filter(Exemplar.id == exemplar_id).first()
    if not exemplar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exemplar com ID {exemplar_id} não encontrado.",
        )

    # Não permitir excluir exemplar emprestado
    tem_emprestimo_ativo = (
        db.query(Emprestimo)
        .filter(
            Emprestimo.exemplar_id == exemplar_id,
            Emprestimo.estado.in_([EstadoEmprestimo.ATIVO, EstadoEmprestimo.ATRASADO]),
        )
        .first()
    )
    if tem_emprestimo_ativo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir exemplar atualmente emprestado.",
        )

    livro_id = exemplar.livro_id
    db.delete(exemplar)
    db.flush()

    # Verificar cancelamento de reservas caso este fosse o último
    verificar_cancelamento_reservas_por_baixa(db, livro_id)
    db.commit()
