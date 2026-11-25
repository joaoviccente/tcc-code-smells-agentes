from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import (
    EstadoExemplar,
    EstadoMulta,
    EstadoReserva,
    PRAZO_RETIRADA_RESERVA_HORAS,
    SituacaoUsuario,
)
from app.models.emprestimo import Emprestimo
from app.models.exemplar import Exemplar
from app.models.livro import Livro
from app.models.multa import Multa
from app.models.reserva import Reserva
from app.models.usuario import Usuario
from app.schemas.reserva import ReservaCreate
from app.services.usuario_service import verificar_e_atualizar_situacao


def reorganizar_fila(db: Session, livro_id: int) -> None:
    reservas_espera = (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == livro_id,
            Reserva.estado == EstadoReserva.AGUARDANDO,
        )
        .order_by(Reserva.data_reserva.asc(), Reserva.id.asc())
        .all()
    )
    for idx, r in enumerate(reservas_espera, start=1):
        r.posicao_fila = idx


def processar_expiracoes_reservas(db: Session, now: datetime | None = None) -> list[Reserva]:
    if now is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

    reservas_disponiveis = (
        db.query(Reserva)
        .filter(
            Reserva.estado == EstadoReserva.DISPONIVEL,
            Reserva.data_disponibilizacao.isnot(None),
        )
        .all()
    )

    expiradas = []
    for res in reservas_disponiveis:
        prazo_limite = res.data_disponibilizacao + timedelta(hours=PRAZO_RETIRADA_RESERVA_HORAS)
        if now > prazo_limite:
            res.estado = EstadoReserva.EXPIRADA
            res.posicao_fila = 0
            exemplar_liberado = None
            if res.exemplar_id:
                exemplar_liberado = db.query(Exemplar).filter(Exemplar.id == res.exemplar_id).first()
            res.exemplar_id = None
            expiradas.append(res)

            # Passa a vez ao próximo da fila (Regra 4)
            proximo = (
                db.query(Reserva)
                .filter(
                    Reserva.livro_id == res.livro_id,
                    Reserva.estado == EstadoReserva.AGUARDANDO,
                )
                .order_by(Reserva.posicao_fila.asc(), Reserva.data_reserva.asc())
                .first()
            )

            if proximo:
                proximo.estado = EstadoReserva.DISPONIVEL
                proximo.data_disponibilizacao = now
                proximo.posicao_fila = 0
                if exemplar_liberado:
                    proximo.exemplar_id = exemplar_liberado.id
                    exemplar_liberado.estado = EstadoExemplar.RESERVADO
            else:
                if exemplar_liberado and exemplar_liberado.estado == EstadoExemplar.RESERVADO:
                    exemplar_liberado.estado = EstadoExemplar.DISPONIVEL

            db.flush()
            reorganizar_fila(db, res.livro_id)

    if expiradas:
        db.commit()
    return expiradas


def criar_reserva(db: Session, reserva_in: ReservaCreate) -> Reserva:
    now = reserva_in.data_reserva or datetime.now(timezone.utc).replace(tzinfo=None)
    processar_expiracoes_reservas(db, now)

    usuario = db.query(Usuario).filter(Usuario.id == reserva_in.usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {reserva_in.usuario_id} não encontrado.",
        )
    verificar_e_atualizar_situacao(db, usuario, now)

    if usuario.situacao == SituacaoUsuario.SUSPENSO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário suspenso não pode realizar reserva.",
        )

    # Verifica multas abertas
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
            detail="Usuário com multa aberta não pode realizar reserva.",
        )

    livro = db.query(Livro).filter(Livro.id == reserva_in.livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {reserva_in.livro_id} não encontrado.",
        )

    # Regra 6: Exemplar em reparo ou baixado não pode ser reservado.
    # Se o livro não tem nenhum exemplar viável (não baixado e não em reparo) ou não tem exemplares
    exemplares_viaveis = (
        db.query(Exemplar)
        .filter(
            Exemplar.livro_id == livro.id,
            Exemplar.estado.notin_([EstadoExemplar.BAIXADO, EstadoExemplar.EM_REPARO]),
        )
        .count()
    )
    if exemplares_viaveis == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Livro não possui exemplares disponíveis para reserva (todos em reparo, baixados ou inexistentes).",
        )

    # Usuário já possui reserva ativa para este livro?
    reserva_existente = (
        db.query(Reserva)
        .filter(
            Reserva.usuario_id == usuario.id,
            Reserva.livro_id == livro.id,
            Reserva.estado.in_([EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL]),
        )
        .first()
    )
    if reserva_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já possui reserva ativa para este livro.",
        )

    # Usuário já possui empréstimo ativo deste livro?
    emprestimo_ativo_mesmo_livro = (
        db.query(Emprestimo)
        .join(Exemplar)
        .filter(
            Emprestimo.usuario_id == usuario.id,
            Exemplar.livro_id == livro.id,
            Emprestimo.data_devolucao.is_(None),
        )
        .first()
    )
    if emprestimo_ativo_mesmo_livro:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já possui exemplar deste livro emprestado.",
        )

    # Posição na fila: total de reservas aguardando + 1
    total_aguardando = (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == livro.id,
            Reserva.estado == EstadoReserva.AGUARDANDO,
        )
        .count()
    )
    posicao = total_aguardando + 1

    reserva = Reserva(
        livro_id=livro.id,
        usuario_id=usuario.id,
        data_reserva=now,
        posicao_fila=posicao,
        estado=EstadoReserva.AGUARDANDO,
    )
    db.add(reserva)
    db.commit()
    db.refresh(reserva)
    return reserva


def cancelar_reserva(db: Session, reserva_id: int, now: datetime | None = None) -> Reserva:
    if now is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
    processar_expiracoes_reservas(db, now)

    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reserva com ID {reserva_id} não encontrada.",
        )

    if reserva.estado not in [EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reserva não pode ser cancelada pois está no estado '{reserva.estado.value}'.",
        )

    livro_id = reserva.livro_id
    exemplar_liberado = None
    if reserva.exemplar_id:
        exemplar_liberado = db.query(Exemplar).filter(Exemplar.id == reserva.exemplar_id).first()

    reserva.estado = EstadoReserva.CANCELADA
    reserva.posicao_fila = 0
    reserva.exemplar_id = None

    # Se a reserva estava disponível e foi cancelada, passa a vez ao próximo (Regra 4)
    if exemplar_liberado:
        proximo = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == livro_id,
                Reserva.estado == EstadoReserva.AGUARDANDO,
            )
            .order_by(Reserva.posicao_fila.asc(), Reserva.data_reserva.asc())
            .first()
        )
        if proximo:
            proximo.estado = EstadoReserva.DISPONIVEL
            proximo.data_disponibilizacao = now
            proximo.posicao_fila = 0
            proximo.exemplar_id = exemplar_liberado.id
            exemplar_liberado.estado = EstadoExemplar.RESERVADO
        else:
            exemplar_liberado.estado = EstadoExemplar.DISPONIVEL

    db.flush()
    reorganizar_fila(db, livro_id)
    db.commit()
    db.refresh(reserva)
    return reserva


def listar_fila_livro(db: Session, livro_id: int) -> list[Reserva]:
    processar_expiracoes_reservas(db)

    livro = db.query(Livro).filter(Livro.id == livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {livro_id} não encontrado.",
        )

    return (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == livro_id,
            Reserva.estado.in_([EstadoReserva.DISPONIVEL, EstadoReserva.AGUARDANDO]),
        )
        .order_by(
            Reserva.estado == EstadoReserva.AGUARDANDO,  # DISPONIVEL vem primeiro
            Reserva.posicao_fila.asc(),
            Reserva.data_reserva.asc(),
        )
        .all()
    )
