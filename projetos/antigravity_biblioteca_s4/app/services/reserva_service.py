from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.config import HORAS_LIMITE_RETIRADA_RESERVA
from app.models.reserva import Reserva
from app.models.livro import Livro
from app.models.usuario import Usuario
from app.models.exemplar import Exemplar
from app.models.emprestimo import Emprestimo
from app.models.multa import Multa
from app.models.enums import (
    EstadoReserva,
    EstadoExemplar,
    EstadoMulta,
    SituacaoUsuario,
)
from app.schemas.reserva import ReservaCreate
from app.services.usuario_service import check_e_atualizar_suspensao


def reordenar_fila(db: Session, livro_id: int) -> None:
    """Reindexa as posições na fila (1, 2, 3...) para reservas aguardando do livro."""
    reservas_aguardando = (
        db.query(Reserva)
        .filter(Reserva.livro_id == livro_id, Reserva.estado == EstadoReserva.AGUARDANDO)
        .order_by(Reserva.data.asc(), Reserva.id.asc())
        .all()
    )
    for idx, r in enumerate(reservas_aguardando, start=1):
        r.posicao_na_fila = idx


def cancelar_todas_reservas_do_livro(db: Session, livro_id: int) -> int:
    """
    Regra 6: se o último exemplar disponível de um livro for baixado,
    todas as reservas daquele livro são canceladas.
    """
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
        r.posicao_na_fila = None
    db.commit()
    return len(reservas_ativas)


def processar_reservas_expiradas(db: Session, current_time: Optional[datetime] = None) -> List[Reserva]:
    """
    Regra 4: Quando um exemplar é devolvido, o primeiro da fila passa ao estado disponível
    e tem 48 horas para retirá-lo; esgotado o prazo, a reserva expira e a vez passa ao próximo.
    """
    agora = current_time or datetime.now()
    reservas_vencidas = (
        db.query(Reserva)
        .filter(
            Reserva.estado == EstadoReserva.DISPONIVEL,
            Reserva.data_limite_retirada.isnot(None),
            Reserva.data_limite_retirada <= agora,
        )
        .all()
    )

    expiradas = []
    for r in reservas_vencidas:
        r.estado = EstadoReserva.EXPIRADA
        r.posicao_na_fila = None
        expiradas.append(r)

        exemplar = r.exemplar
        livro_id = r.livro_id

        # Busca o próximo na fila
        proxima = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == livro_id,
                Reserva.estado == EstadoReserva.AGUARDANDO,
            )
            .order_by(Reserva.posicao_na_fila.asc(), Reserva.data.asc())
            .first()
        )

        if proxima:
            proxima.estado = EstadoReserva.DISPONIVEL
            proxima.data_limite_retirada = agora + timedelta(hours=HORAS_LIMITE_RETIRADA_RESERVA)
            if exemplar:
                proxima.exemplar_id = exemplar.id
                exemplar.estado = EstadoExemplar.RESERVADO
            reordenar_fila(db, livro_id)
        else:
            # Sem mais reservas na fila para este livro: se o exemplar estava reservado, volta a disponível
            if exemplar and exemplar.estado == EstadoExemplar.RESERVADO:
                exemplar.estado = EstadoExemplar.DISPONIVEL

    db.commit()
    return expiradas


def create_reserva(db: Session, reserva_in: ReservaCreate) -> Reserva:
    processar_reservas_expiradas(db)

    # 1. Validar usuário
    usuario = db.query(Usuario).filter(Usuario.id == reserva_in.usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {reserva_in.usuario_id} não encontrado.",
        )
    check_e_atualizar_suspensao(usuario)
    if usuario.situacao == SituacaoUsuario.SUSPENSO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reserva não permitida: usuário está suspenso.",
        )

    # Verificar multas abertas
    tem_multa_aberta = (
        db.query(Multa)
        .join(Emprestimo)
        .filter(
            Emprestimo.usuario_id == usuario.id,
            Multa.estado == EstadoMulta.ABERTA,
        )
        .first()
    )
    if tem_multa_aberta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reserva não permitida: usuário possui multas em aberto pendentes de pagamento.",
        )

    # 2. Validar livro
    livro = db.query(Livro).filter(Livro.id == reserva_in.livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {reserva_in.livro_id} não encontrado.",
        )

    # Regra 6: "Exemplar em reparo ou baixado não pode ser emprestado nem reservado"
    exemplares = livro.exemplares
    if not exemplares:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível reservar livro sem exemplares cadastrados no acervo.",
        )

    # Se todos os exemplares estiverem em reparo ou baixados, não pode ser reservado
    exemplares_validos = [e for e in exemplares if e.estado not in (EstadoExemplar.BAIXADO, EstadoExemplar.EM_REPARO)]
    if not exemplares_validos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível reservar livro cujos exemplares estão todos baixados ou em reparo.",
        )

    # 3. Verificar se o usuário já possui reserva ativa para este livro
    reserva_existente = (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == reserva_in.livro_id,
            Reserva.usuario_id == reserva_in.usuario_id,
            Reserva.estado.in_([EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL]),
        )
        .first()
    )
    if reserva_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já possui reserva ativa para este livro.",
        )

    data_reserva = reserva_in.data or datetime.now()

    # Posição na fila de aguardando
    max_pos = (
        db.query(func.max(Reserva.posicao_na_fila))
        .filter(Reserva.livro_id == reserva_in.livro_id, Reserva.estado == EstadoReserva.AGUARDANDO)
        .scalar()
    ) or 0

    nova_reserva = Reserva(
        livro_id=reserva_in.livro_id,
        usuario_id=reserva_in.usuario_id,
        data=data_reserva,
        posicao_na_fila=max_pos + 1,
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
            detail=f"Reserva com ID {reserva_id} não encontrada.",
        )

    if reserva.estado in (EstadoReserva.CANCELADA, EstadoReserva.EXPIRADA, EstadoReserva.CONCLUIDA):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reserva não pode ser cancelada pois está com estado '{reserva.estado.value}'.",
        )

    livro_id = reserva.livro_id
    exemplar = reserva.exemplar

    if reserva.estado == EstadoReserva.DISPONIVEL:
        reserva.estado = EstadoReserva.CANCELADA
        reserva.posicao_na_fila = None

        # Passar exemplar para o próximo da fila
        proxima = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == livro_id,
                Reserva.estado == EstadoReserva.AGUARDANDO,
            )
            .order_by(Reserva.posicao_na_fila.asc(), Reserva.data.asc())
            .first()
        )

        if proxima:
            proxima.estado = EstadoReserva.DISPONIVEL
            proxima.data_limite_retirada = datetime.now() + timedelta(hours=HORAS_LIMITE_RETIRADA_RESERVA)
            if exemplar:
                proxima.exemplar_id = exemplar.id
                exemplar.estado = EstadoExemplar.RESERVADO
            reordenar_fila(db, livro_id)
        else:
            if exemplar and exemplar.estado == EstadoExemplar.RESERVADO:
                exemplar.estado = EstadoExemplar.DISPONIVEL

    elif reserva.estado == EstadoReserva.AGUARDANDO:
        reserva.estado = EstadoReserva.CANCELADA
        reserva.posicao_na_fila = None
        db.flush()
        reordenar_fila(db, livro_id)

    db.commit()
    db.refresh(reserva)
    return reserva


def get_reserva_by_id(db: Session, reserva_id: int) -> Reserva:
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reserva com ID {reserva_id} não encontrada.",
        )
    return reserva


def get_reservas(
    db: Session,
    livro_id: Optional[int] = None,
    usuario_id: Optional[int] = None,
    estado: Optional[EstadoReserva] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Reserva]:
    processar_reservas_expiradas(db)
    query = db.query(Reserva)
    if livro_id:
        query = query.filter(Reserva.livro_id == livro_id)
    if usuario_id:
        query = query.filter(Reserva.usuario_id == usuario_id)
    if estado:
        query = query.filter(Reserva.estado == estado)
    return query.order_by(Reserva.data.desc()).offset(skip).limit(limit).all()


def listar_fila_do_livro(db: Session, livro_id: int) -> List[Reserva]:
    """Lista a fila ativa de reservas de um livro (aguardando e disponível)."""
    # Verifica se livro existe
    livro = db.query(Livro).filter(Livro.id == livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {livro_id} não encontrado.",
        )
    processar_reservas_expiradas(db)
    return (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == livro_id,
            Reserva.estado.in_([EstadoReserva.DISPONIVEL, EstadoReserva.AGUARDANDO]),
        )
        .order_by(
            # Disponíveis vêm primeiro na fila, depois ordenados por posicao_na_fila
            Reserva.estado.desc(),
            Reserva.posicao_na_fila.asc(),
            Reserva.data.asc(),
        )
        .all()
    )
