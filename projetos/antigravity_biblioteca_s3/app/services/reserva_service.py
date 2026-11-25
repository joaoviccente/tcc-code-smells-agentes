from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.config import HORAS_LIMITE_RETIRADA_RESERVA
from app.models import Reserva, Livro, Usuario, Exemplar
from app.models.enums import EstadoReserva, EstadoExemplar, SituacaoUsuario
from app.schemas.reserva import ReservaCreate
from app.utils import get_utcnow


def reorganizar_fila(db: Session, livro_id: int) -> None:
    """
    Reorganiza as posições da fila para um livro:
    Se houver reserva 'disponivel', ela fica na posição 1.
    As reservas 'aguardando' recebem posições sequenciais seguintes.
    """
    db.flush()
    reserva_disponivel = db.query(Reserva).filter(
        Reserva.livro_id == livro_id,
        Reserva.estado == EstadoReserva.DISPONIVEL
    ).first()

    offset = 1
    if reserva_disponivel:
        reserva_disponivel.posicao_fila = 1
        offset = 2

    reservas_aguardando = db.query(Reserva).filter(
        Reserva.livro_id == livro_id,
        Reserva.estado == EstadoReserva.AGUARDANDO
    ).order_by(Reserva.data.asc()).all()

    for idx, r in enumerate(reservas_aguardando, start=offset):
        r.posicao_fila = idx

    db.flush()


def processar_reservas_expiradas(db: Session, now: Optional[datetime] = None) -> List[Reserva]:
    """
    Regra 4: esgotado o prazo de 48 horas, a reserva expira e a vez passa ao próximo.
    """
    if now is None:
        now = get_utcnow()

    expiradas = db.query(Reserva).filter(
        Reserva.estado == EstadoReserva.DISPONIVEL,
        Reserva.data_limite_retirada.isnot(None),
        Reserva.data_limite_retirada < now
    ).all()

    reservas_processadas = []
    for r in expiradas:
        r.estado = EstadoReserva.EXPIRADA
        r.posicao_fila = None
        exemplar_vinculado = r.exemplar
        livro_id = r.livro_id
        r.exemplar_id = None
        reservas_processadas.append(r)
        db.flush()

        # Buscar próxima reserva na fila
        proxima = db.query(Reserva).filter(
            Reserva.livro_id == livro_id,
            Reserva.estado == EstadoReserva.AGUARDANDO
        ).order_by(Reserva.data.asc()).first()

        if proxima:
            proxima.estado = EstadoReserva.DISPONIVEL
            proxima.posicao_fila = 1
            proxima.data_limite_retirada = now + timedelta(hours=HORAS_LIMITE_RETIRADA_RESERVA)
            if exemplar_vinculado:
                proxima.exemplar_id = exemplar_vinculado.id
                exemplar_vinculado.estado = EstadoExemplar.RESERVADO
        else:
            if exemplar_vinculado:
                exemplar_vinculado.estado = EstadoExemplar.DISPONIVEL

        db.flush()
        reorganizar_fila(db, livro_id)

    db.commit()
    return reservas_processadas


def create_reserva(db: Session, reserva_in: ReservaCreate) -> Reserva:
    now = reserva_in.data or get_utcnow()
    processar_reservas_expiradas(db, now=now)

    livro = db.query(Livro).filter(Livro.id == reserva_in.livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {reserva_in.livro_id} não encontrado."
        )

    usuario = db.query(Usuario).filter(Usuario.id == reserva_in.usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {reserva_in.usuario_id} não encontrado."
        )

    # Regra 6: Exemplar em reparo ou baixado não pode ser reservado.
    # Se todos os exemplares forem baixados ou em reparo, não permite reserva.
    exemplares_aptos = db.query(Exemplar).filter(
        Exemplar.livro_id == reserva_in.livro_id,
        ~Exemplar.estado.in_([EstadoExemplar.BAIXADO, EstadoExemplar.EM_REPARO])
    ).count()

    if exemplares_aptos == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível reservar este livro: todos os exemplares estão em reparo ou baixados."
        )

    # Verificar se o usuário já possui reserva ativa para este livro
    reserva_existente = db.query(Reserva).filter(
        Reserva.livro_id == reserva_in.livro_id,
        Reserva.usuario_id == reserva_in.usuario_id,
        Reserva.estado.in_([EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL])
    ).first()
    if reserva_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já possui reserva ativa para este livro."
        )

    # Calcular posição na fila
    qtd_fila = db.query(Reserva).filter(
        Reserva.livro_id == reserva_in.livro_id,
        Reserva.estado.in_([EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL])
    ).count()

    nova_reserva = Reserva(
        livro_id=reserva_in.livro_id,
        usuario_id=reserva_in.usuario_id,
        data=now,
        posicao_fila=qtd_fila + 1,
        estado=EstadoReserva.AGUARDANDO,
    )
    db.add(nova_reserva)
    db.commit()
    db.refresh(nova_reserva)
    return nova_reserva


def cancelar_reserva(db: Session, reserva_id: int) -> Reserva:
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reserva com ID {reserva_id} não encontrada."
        )

    if reserva.estado in [EstadoReserva.CANCELADA, EstadoReserva.EXPIRADA]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reserva já se encontra no estado '{reserva.estado.value}'."
        )

    livro_id = reserva.livro_id
    exemplar_vinculado = reserva.exemplar
    estava_disponivel = (reserva.estado == EstadoReserva.DISPONIVEL)

    reserva.estado = EstadoReserva.CANCELADA
    reserva.posicao_fila = None
    reserva.exemplar_id = None
    reserva.data_limite_retirada = None
    db.commit()

    if estava_disponivel:
        # Passar a vez para o próximo da fila
        proxima = db.query(Reserva).filter(
            Reserva.livro_id == livro_id,
            Reserva.estado == EstadoReserva.AGUARDANDO
        ).order_by(Reserva.data.asc()).first()

        now = get_utcnow()
        if proxima:
            proxima.estado = EstadoReserva.DISPONIVEL
            proxima.data_limite_retirada = now + timedelta(hours=HORAS_LIMITE_RETIRADA_RESERVA)
            if exemplar_vinculado:
                proxima.exemplar_id = exemplar_vinculado.id
                exemplar_vinculado.estado = EstadoExemplar.RESERVADO
        else:
            if exemplar_vinculado:
                exemplar_vinculado.estado = EstadoExemplar.DISPONIVEL

    reorganizar_fila(db, livro_id)
    db.refresh(reserva)
    return reserva


def get_fila_livro(db: Session, livro_id: int) -> List[Reserva]:
    livro = db.query(Livro).filter(Livro.id == livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {livro_id} não encontrado."
        )

    processar_reservas_expiradas(db)
    reorganizar_fila(db, livro_id)

    return db.query(Reserva).filter(
        Reserva.livro_id == livro_id,
        Reserva.estado.in_([EstadoReserva.DISPONIVEL, EstadoReserva.AGUARDANDO])
    ).order_by(Reserva.posicao_fila.asc()).all()


def get_reserva_by_id(db: Session, reserva_id: int) -> Reserva:
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reserva com ID {reserva_id} não encontrada."
        )
    return reserva


def get_reservas(
    db: Session,
    usuario_id: Optional[int] = None,
    livro_id: Optional[int] = None,
    estado: Optional[EstadoReserva] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Reserva]:
    processar_reservas_expiradas(db)
    query = db.query(Reserva)
    if usuario_id:
        query = query.filter(Reserva.usuario_id == usuario_id)
    if livro_id:
        query = query.filter(Reserva.livro_id == livro_id)
    if estado:
        query = query.filter(Reserva.estado == estado)
    return query.order_by(Reserva.data.desc()).offset(skip).limit(limit).all()
