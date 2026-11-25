from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import EstadoExemplar, EstadoReserva
from app.models.exemplar import Exemplar
from app.models.livro import Livro
from app.models.reserva import Reserva
from app.schemas.exemplar import ExemplarCreate, ExemplarUpdate


def cancelar_reservas_se_sem_exemplar_ativo(db: Session, livro_id: int) -> int:
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
        for r in reservas_ativas:
            r.estado = EstadoReserva.CANCELADA
            r.posicao_fila = 0
            r.exemplar_id = None
        db.commit()
        return len(reservas_ativas)
    return 0


def criar_exemplar(db: Session, exemplar_in: ExemplarCreate) -> Exemplar:
    livro = db.query(Livro).filter(Livro.id == exemplar_in.livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {exemplar_in.livro_id} não encontrado.",
        )

    if db.query(Exemplar).filter(Exemplar.codigo_tombo == exemplar_in.codigo_tombo).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Código de tombo '{exemplar_in.codigo_tombo}' já cadastrado.",
        )

    exemplar = Exemplar(
        livro_id=exemplar_in.livro_id,
        codigo_tombo=exemplar_in.codigo_tombo,
        estado=exemplar_in.estado,
    )
    db.add(exemplar)
    db.commit()
    db.refresh(exemplar)
    return exemplar


def listar_exemplares(
    db: Session,
    livro_id: int | None = None,
    estado: EstadoExemplar | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Exemplar]:
    query = db.query(Exemplar)
    if livro_id:
        query = query.filter(Exemplar.livro_id == livro_id)
    if estado:
        query = query.filter(Exemplar.estado == estado)
    return query.offset(skip).limit(limit).all()


def obter_exemplar_por_id(db: Session, exemplar_id: int) -> Exemplar:
    exemplar = db.query(Exemplar).filter(Exemplar.id == exemplar_id).first()
    if not exemplar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exemplar com ID {exemplar_id} não encontrado.",
        )
    return exemplar


def atualizar_exemplar(db: Session, exemplar_id: int, exemplar_in: ExemplarUpdate) -> Exemplar:
    exemplar = obter_exemplar_por_id(db, exemplar_id)

    if exemplar_in.livro_id and exemplar_in.livro_id != exemplar.livro_id:
        livro = db.query(Livro).filter(Livro.id == exemplar_in.livro_id).first()
        if not livro:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Livro com ID {exemplar_in.livro_id} não encontrado.",
            )
        exemplar.livro_id = exemplar_in.livro_id

    if exemplar_in.codigo_tombo and exemplar_in.codigo_tombo != exemplar.codigo_tombo:
        if db.query(Exemplar).filter(Exemplar.codigo_tombo == exemplar_in.codigo_tombo).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Código de tombo '{exemplar_in.codigo_tombo}' já cadastrado.",
            )
        exemplar.codigo_tombo = exemplar_in.codigo_tombo

    if exemplar_in.estado is not None:
        exemplar.estado = exemplar_in.estado

    db.commit()
    db.refresh(exemplar)

    # Regra 6: Se o exemplar foi baixado, verificar se deve cancelar reservas
    if exemplar.estado == EstadoExemplar.BAIXADO:
        cancelar_reservas_se_sem_exemplar_ativo(db, exemplar.livro_id)

    return exemplar


def deletar_exemplar(db: Session, exemplar_id: int) -> None:
    exemplar = obter_exemplar_por_id(db, exemplar_id)

    if exemplar.estado == EstadoExemplar.EMPRESTADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir exemplar atualmente emprestado.",
        )

    livro_id = exemplar.livro_id
    db.delete(exemplar)
    db.commit()

    # Regra 6 após deleção
    cancelar_reservas_se_sem_exemplar_ativo(db, livro_id)
