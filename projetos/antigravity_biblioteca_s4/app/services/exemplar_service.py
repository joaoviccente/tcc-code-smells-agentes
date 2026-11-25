from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.exemplar import Exemplar
from app.models.livro import Livro
from app.models.enums import EstadoExemplar, EstadoEmprestimo
from app.schemas.exemplar import ExemplarCreate, ExemplarUpdate
from app.services.reserva_service import cancelar_todas_reservas_do_livro


def get_exemplares(
    db: Session,
    livro_id: Optional[int] = None,
    estado: Optional[EstadoExemplar] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Exemplar]:
    query = db.query(Exemplar)
    if livro_id:
        query = query.filter(Exemplar.livro_id == livro_id)
    if estado:
        query = query.filter(Exemplar.estado == estado)
    return query.offset(skip).limit(limit).all()


def get_exemplar_by_id(db: Session, exemplar_id: int) -> Exemplar:
    exemplar = db.query(Exemplar).filter(Exemplar.id == exemplar_id).first()
    if not exemplar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exemplar com ID {exemplar_id} não encontrado.",
        )
    return exemplar


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
            detail=f"Já existe um exemplar cadastrado com o código de tombo '{exemplar_in.codigo_tombo}'.",
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


def update_exemplar(db: Session, exemplar_id: int, exemplar_in: ExemplarUpdate) -> Exemplar:
    exemplar = get_exemplar_by_id(db, exemplar_id)

    if exemplar_in.livro_id is not None and exemplar_in.livro_id != exemplar.livro_id:
        livro = db.query(Livro).filter(Livro.id == exemplar_in.livro_id).first()
        if not livro:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Livro com ID {exemplar_in.livro_id} não encontrado.",
            )
        exemplar.livro_id = exemplar_in.livro_id

    if exemplar_in.codigo_tombo is not None and exemplar_in.codigo_tombo != exemplar.codigo_tombo:
        if db.query(Exemplar).filter(Exemplar.codigo_tombo == exemplar_in.codigo_tombo).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe um exemplar com o código de tombo '{exemplar_in.codigo_tombo}'.",
            )
        exemplar.codigo_tombo = exemplar_in.codigo_tombo

    mudou_para_baixado = False
    if exemplar_in.estado is not None:
        if exemplar_in.estado == EstadoExemplar.BAIXADO and exemplar.estado != EstadoExemplar.BAIXADO:
            mudou_para_baixado = True
        exemplar.estado = exemplar_in.estado

    db.commit()
    db.refresh(exemplar)

    # Regra 6: se o último exemplar disponível de um livro for baixado, todas as reservas daquele livro são canceladas
    if mudou_para_baixado:
        outros_nao_baixados = (
            db.query(Exemplar)
            .filter(
                Exemplar.livro_id == exemplar.livro_id,
                Exemplar.id != exemplar.id,
                Exemplar.estado != EstadoExemplar.BAIXADO,
            )
            .count()
        )
        if outros_nao_baixados == 0:
            cancelar_todas_reservas_do_livro(db, exemplar.livro_id)

    return exemplar


def delete_exemplar(db: Session, exemplar_id: int) -> None:
    exemplar = get_exemplar_by_id(db, exemplar_id)
    tem_emprestimos_ativos = any(
        emp.estado in (EstadoEmprestimo.ATIVO, EstadoEmprestimo.ATRASADO)
        for emp in exemplar.emprestimos
    )
    if tem_emprestimos_ativos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir exemplar que possui empréstimos ativos.",
        )
    db.delete(exemplar)
    db.commit()
