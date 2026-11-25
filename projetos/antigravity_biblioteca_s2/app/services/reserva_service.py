from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.enums import EstadoExemplar, EstadoReserva, SituacaoUsuario
from app.models.exemplar import Exemplar
from app.models.livro import Livro
from app.models.reserva import Reserva
from app.models.usuario import Usuario
from app.schemas.reserva import ReservaCreate
from app.services.regras import HORAS_EXPIRACAO_RESERVA
from app.services.usuario_service import atualizar_situacao_usuario


def reordenar_fila_aguardando(db: Session, livro_id: int) -> None:
    reservas_aguardando = (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == livro_id,
            Reserva.estado == EstadoReserva.AGUARDANDO,
        )
        .order_by(Reserva.posicao_fila.asc(), Reserva.data.asc())
        .all()
    )
    for idx, r in enumerate(reservas_aguardando, start=1):
        r.posicao_fila = idx


def processar_expiracoes(db: Session, data_referencia: Optional[datetime] = None) -> List[Reserva]:
    if data_referencia is None:
        data_referencia = datetime.now(timezone.utc)
    elif data_referencia.tzinfo is None:
        data_referencia = data_referencia.replace(tzinfo=timezone.utc)

    reservas_disponiveis = (
        db.query(Reserva)
        .filter(
            Reserva.estado == EstadoReserva.DISPONIVEL,
            Reserva.data_limite_retirada.isnot(None),
        )
        .all()
    )

    expiradas = []
    for res in reservas_disponiveis:
        limite = (
            res.data_limite_retirada
            if res.data_limite_retirada.tzinfo
            else res.data_limite_retirada.replace(tzinfo=timezone.utc)
        )
        if data_referencia > limite:
            res.estado = EstadoReserva.EXPIRADA
            res.posicao_fila = 0
            expiradas.append(res)

            # Passa a vez para o próximo da fila
            proxima = (
                db.query(Reserva)
                .filter(
                    Reserva.livro_id == res.livro_id,
                    Reserva.estado == EstadoReserva.AGUARDANDO,
                )
                .order_by(Reserva.posicao_fila.asc(), Reserva.data.asc())
                .first()
            )
            if proxima:
                proxima.estado = EstadoReserva.DISPONIVEL
                proxima.data_disponibilizacao = data_referencia
                proxima.data_limite_retirada = data_referencia + timedelta(hours=HORAS_EXPIRACAO_RESERVA)
                proxima.posicao_fila = 1
                reordenar_fila_aguardando(db, res.livro_id)
            else:
                # Nenhum outro esperando: liberar exemplar reservado para disponivel
                exemplar_reservado = (
                    db.query(Exemplar)
                    .filter(
                        Exemplar.livro_id == res.livro_id,
                        Exemplar.estado == EstadoExemplar.RESERVADO,
                    )
                    .first()
                )
                if exemplar_reservado:
                    exemplar_reservado.estado = EstadoExemplar.DISPONIVEL

    if expiradas:
        db.commit()

    return expiradas


def create_reserva(db: Session, reserva_in: ReservaCreate) -> Reserva:
    data_operacao = reserva_in.data or datetime.now(timezone.utc)
    if data_operacao.tzinfo is None:
        data_operacao = data_operacao.replace(tzinfo=timezone.utc)

    # Processar expirações primeiro
    processar_expiracoes(db, data_operacao)

    usuario = db.query(Usuario).filter(Usuario.id == reserva_in.usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {reserva_in.usuario_id} não encontrado.",
        )
    atualizar_situacao_usuario(db, usuario, data_operacao)

    if usuario.situacao != SituacaoUsuario.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário suspenso não pode realizar reservas.",
        )

    livro = db.query(Livro).filter(Livro.id == reserva_in.livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {reserva_in.livro_id} não encontrado.",
        )

    # Regra 6: Exemplar em reparo ou baixado não pode ser emprestado nem reservado
    # Se todos os exemplares forem em reparo ou baixados, ou não houver exemplares
    exemplares_validos = (
        db.query(Exemplar)
        .filter(
            Exemplar.livro_id == reserva_in.livro_id,
            ~Exemplar.estado.in_([EstadoExemplar.BAIXADO, EstadoExemplar.EM_REPARO]),
        )
        .count()
    )
    if exemplares_validos == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível reservar livro cujos exemplares estejam em reparo ou baixados.",
        )

    # Verificar se o usuário já tem reserva ativa (aguardando ou disponível) para este livro
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
            status_code=status.HTTP_409_CONFLICT,
            detail="Usuário já possui uma reserva ativa para este livro.",
        )

    # Calcular posição na fila
    qtd_aguardando = (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == reserva_in.livro_id,
            Reserva.estado == EstadoReserva.AGUARDANDO,
        )
        .count()
    )
    nova_posicao = qtd_aguardando + 1

    reserva = Reserva(
        livro_id=reserva_in.livro_id,
        usuario_id=reserva_in.usuario_id,
        data=data_operacao,
        posicao_fila=nova_posicao,
        estado=EstadoReserva.AGUARDANDO,
    )
    db.add(reserva)
    db.commit()
    db.refresh(reserva)
    return reserva


def cancel_reserva(
    db: Session, reserva_id: int, data_referencia: Optional[datetime] = None
) -> Reserva:
    if data_referencia is None:
        data_referencia = datetime.now(timezone.utc)
    elif data_referencia.tzinfo is None:
        data_referencia = data_referencia.replace(tzinfo=timezone.utc)

    processar_expiracoes(db, data_referencia)

    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reserva com ID {reserva_id} não encontrada.",
        )

    if reserva.estado in [EstadoReserva.CANCELADA, EstadoReserva.EXPIRADA]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reserva já se encontra {reserva.estado.value}.",
        )

    livro_id = reserva.livro_id
    estado_anterior = reserva.estado
    reserva.estado = EstadoReserva.CANCELADA
    reserva.posicao_fila = 0

    if estado_anterior == EstadoReserva.DISPONIVEL:
        # Se estava disponível, passar para a próxima reserva aguardando
        proxima = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == livro_id,
                Reserva.estado == EstadoReserva.AGUARDANDO,
            )
            .order_by(Reserva.posicao_fila.asc(), Reserva.data.asc())
            .first()
        )
        if proxima:
            proxima.estado = EstadoReserva.DISPONIVEL
            proxima.data_disponibilizacao = data_referencia
            proxima.data_limite_retirada = data_referencia + timedelta(hours=HORAS_EXPIRACAO_RESERVA)
            proxima.posicao_fila = 1
            reordenar_fila_aguardando(db, livro_id)
        else:
            # Não tem mais ninguém na fila: liberar exemplar reservado
            exemplar_reservado = (
                db.query(Exemplar)
                .filter(
                    Exemplar.livro_id == livro_id,
                    Exemplar.estado == EstadoExemplar.RESERVADO,
                )
                .first()
            )
            if exemplar_reservado:
                exemplar_reservado.estado = EstadoExemplar.DISPONIVEL
    else:
        # Estava aguardando: apenas reordenar a fila
        reordenar_fila_aguardando(db, livro_id)

    db.commit()
    db.refresh(reserva)
    return reserva


def list_fila_livro(
    db: Session, livro_id: int, data_referencia: Optional[datetime] = None
) -> List[Reserva]:
    livro = db.query(Livro).filter(Livro.id == livro_id).first()
    if not livro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Livro com ID {livro_id} não encontrado.",
        )

    processar_expiracoes(db, data_referencia)

    return (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == livro_id,
            Reserva.estado.in_([EstadoReserva.DISPONIVEL, EstadoReserva.AGUARDANDO]),
        )
        .order_by(
            # DISPONIVEL primeiro, depois AGUARDANDO por posicao_fila
            Reserva.estado.desc(),
            Reserva.posicao_fila.asc(),
            Reserva.data.asc(),
        )
        .all()
    )


def list_reservas(
    db: Session,
    livro_id: Optional[int] = None,
    usuario_id: Optional[int] = None,
    estado: Optional[EstadoReserva] = None,
    skip: int = 0,
    limit: int = 100,
    data_referencia: Optional[datetime] = None,
) -> List[Reserva]:
    processar_expiracoes(db, data_referencia)
    query = db.query(Reserva)
    if livro_id is not None:
        query = query.filter(Reserva.livro_id == livro_id)
    if usuario_id is not None:
        query = query.filter(Reserva.usuario_id == usuario_id)
    if estado is not None:
        query = query.filter(Reserva.estado == estado)
    return query.order_by(Reserva.data.desc()).offset(skip).limit(limit).all()


def get_reserva(
    db: Session, reserva_id: int, data_referencia: Optional[datetime] = None
) -> Reserva:
    processar_expiracoes(db, data_referencia)
    reserva = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not reserva:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reserva com ID {reserva_id} não encontrada.",
        )
    return reserva
