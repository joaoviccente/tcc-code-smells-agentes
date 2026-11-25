from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import (
    CategoriaUsuario,
    EstadoEmprestimo,
    EstadoExemplar,
    EstadoMulta,
    EstadoReserva,
    REGRAS_POR_CATEGORIA,
    SituacaoUsuario,
)
from app.models.emprestimo import Emprestimo
from app.models.exemplar import Exemplar
from app.models.multa import Multa
from app.models.reserva import Reserva
from app.models.usuario import Usuario
from app.schemas.emprestimo import EmprestimoCreate, EmprestimoDevolucao
from app.services.exemplar_service import cancelar_reservas_se_sem_exemplar_ativo
from app.services.reserva_service import processar_expiracoes_reservas, reorganizar_fila
from app.services.usuario_service import verificar_e_atualizar_situacao


def atualizar_emprestimos_atrasados(db: Session, now: datetime | None = None) -> None:
    if now is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

    emprestimos_vencidos = (
        db.query(Emprestimo)
        .filter(
            Emprestimo.data_devolucao.is_(None),
            Emprestimo.data_prevista < now,
            Emprestimo.estado == EstadoEmprestimo.ATIVO,
        )
        .all()
    )
    for emp in emprestimos_vencidos:
        emp.estado = EstadoEmprestimo.ATRASADO
        dias = (now.date() - emp.data_prevista.date()).days
        # Regra 2: atraso superior a 15 dias suspende o usuário pelo dobro dos dias de atraso
        if dias > 15:
            emp.usuario.situacao = SituacaoUsuario.SUSPENSO
            nova_suspensao = now + timedelta(days=2 * dias)
            if emp.usuario.suspenso_ate is None or nova_suspensao > emp.usuario.suspenso_ate:
                emp.usuario.suspenso_ate = nova_suspensao

    if emprestimos_vencidos:
        db.commit()


def criar_emprestimo(db: Session, emprestimo_in: EmprestimoCreate) -> Emprestimo:
    now = emprestimo_in.data_retirada or datetime.now(timezone.utc).replace(tzinfo=None)
    atualizar_emprestimos_atrasados(db, now)
    processar_expiracoes_reservas(db, now)

    # 1. Validação do Usuário
    usuario = db.query(Usuario).filter(Usuario.id == emprestimo_in.usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {emprestimo_in.usuario_id} não encontrado.",
        )
    verificar_e_atualizar_situacao(db, usuario, now)

    # Regra 1: Empréstimo só é permitido a usuário ativo
    if usuario.situacao != SituacaoUsuario.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo não permitido: usuário está suspenso.",
        )

    # Regra 1: sem multa aberta
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
            detail="Empréstimo não permitido: usuário possui multa em aberto.",
        )

    # Regra 1: abaixo do seu limite de exemplares
    regras = REGRAS_POR_CATEGORIA[usuario.categoria]
    total_ativos = (
        db.query(Emprestimo)
        .filter(
            Emprestimo.usuario_id == usuario.id,
            Emprestimo.data_devolucao.is_(None),
        )
        .count()
    )
    if total_ativos >= regras.limite_exemplares:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Empréstimo não permitido: limite de {regras.limite_exemplares} exemplar(es) atingido para a categoria '{usuario.categoria.value}'.",
        )

    # 2. Validação do Exemplar
    exemplar = db.query(Exemplar).filter(Exemplar.id == emprestimo_in.exemplar_id).first()
    if not exemplar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exemplar com ID {emprestimo_in.exemplar_id} não encontrado.",
        )

    # Regra 6: Exemplar em reparo ou baixado não pode ser emprestado nem reservado
    if exemplar.estado == EstadoExemplar.EM_REPARO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exemplar em reparo não pode ser emprestado.",
        )
    if exemplar.estado == EstadoExemplar.BAIXADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exemplar baixado não pode ser emprestado.",
        )
    if exemplar.estado == EstadoExemplar.EMPRESTADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exemplar já se encontra emprestado.",
        )

    # Se estiver reservado, só pode ser retirado pelo usuário titular da reserva disponível
    if exemplar.estado == EstadoExemplar.RESERVADO:
        reserva_disponivel = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == exemplar.livro_id,
                Reserva.estado == EstadoReserva.DISPONIVEL,
                (Reserva.exemplar_id == exemplar.id) | (Reserva.exemplar_id.is_(None)),
            )
            .first()
        )
        if reserva_disponivel and reserva_disponivel.usuario_id != usuario.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Exemplar reservado para outro usuário.",
            )

    # Se estiver disponível, verificar se há reserva disponível prioritária para outro usuário
    if exemplar.estado == EstadoExemplar.DISPONIVEL:
        reserva_outro = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == exemplar.livro_id,
                Reserva.estado == EstadoReserva.DISPONIVEL,
                Reserva.usuario_id != usuario.id,
            )
            .first()
        )
        if reserva_outro:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Existe reserva prioritária disponível para outro usuário deste livro.",
            )

    # Se este usuário tinha uma reserva ativa para este livro, conclui a reserva
    minha_reserva = (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == exemplar.livro_id,
            Reserva.usuario_id == usuario.id,
            Reserva.estado.in_([EstadoReserva.DISPONIVEL, EstadoReserva.AGUARDANDO]),
        )
        .first()
    )
    if minha_reserva:
        minha_reserva.estado = EstadoReserva.CONCLUIDA
        minha_reserva.posicao_fila = 0
        minha_reserva.exemplar_id = None
        reorganizar_fila(db, exemplar.livro_id)

    # 3. Cria o empréstimo
    data_prevista = now + timedelta(days=regras.prazo_dias)
    emprestimo = Emprestimo(
        exemplar_id=exemplar.id,
        usuario_id=usuario.id,
        data_retirada=now,
        data_prevista=data_prevista,
        data_devolucao=None,
        estado=EstadoEmprestimo.ATIVO,
        numero_renovacoes=0,
    )
    exemplar.estado = EstadoExemplar.EMPRESTADO

    db.add(emprestimo)
    db.commit()
    db.refresh(emprestimo)
    return emprestimo


def renovar_emprestimo(db: Session, emprestimo_id: int, now: datetime | None = None) -> Emprestimo:
    if now is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
    atualizar_emprestimos_atrasados(db, now)
    processar_expiracoes_reservas(db, now)

    emprestimo = db.query(Emprestimo).filter(Emprestimo.id == emprestimo_id).first()
    if not emprestimo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Empréstimo com ID {emprestimo_id} não encontrado.",
        )

    if emprestimo.data_devolucao is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível renovar um empréstimo já devolvido.",
        )

    usuario = emprestimo.usuario
    verificar_e_atualizar_situacao(db, usuario, now)
    if usuario.situacao != SituacaoUsuario.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário suspenso não pode renovar empréstimo.",
        )

    # Regra 3: A renovação é negada se o empréstimo estiver atrasado
    if emprestimo.estado == EstadoEmprestimo.ATRASADO or now.date() > emprestimo.data_prevista.date():
        emprestimo.estado = EstadoEmprestimo.ATRASADO
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação negada: o empréstimo está atrasado.",
        )

    # Regra 3: se o limite de renovações da categoria já tiver sido atingido
    regras = REGRAS_POR_CATEGORIA[usuario.categoria]
    if emprestimo.numero_renovacoes >= regras.limite_renovacoes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Renovação negada: limite de {regras.limite_renovacoes} renovação(ões) atingido para a categoria '{usuario.categoria.value}'.",
        )

    # Regra 3: se houver fila de reserva para aquele livro
    livro_id = emprestimo.exemplar.livro_id
    fila_reserva = (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == livro_id,
            Reserva.estado.in_([EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL]),
        )
        .count()
    )
    if fila_reserva > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação negada: há reservas na fila para este livro.",
        )

    # Efetua renovação
    emprestimo.numero_renovacoes += 1
    emprestimo.data_prevista = emprestimo.data_prevista + timedelta(days=regras.prazo_dias)

    db.commit()
    db.refresh(emprestimo)
    return emprestimo


def devolver_emprestimo(
    db: Session,
    emprestimo_id: int,
    devolucao_in: EmprestimoDevolucao | None = None,
) -> Emprestimo:
    now = (
        devolucao_in.data_devolucao
        if devolucao_in and devolucao_in.data_devolucao
        else datetime.now(timezone.utc).replace(tzinfo=None)
    )

    emprestimo = db.query(Emprestimo).filter(Emprestimo.id == emprestimo_id).first()
    if not emprestimo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Empréstimo com ID {emprestimo_id} não encontrado.",
        )

    if emprestimo.data_devolucao is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exemplar já foi devolvido anteriormente.",
        )

    usuario = emprestimo.usuario
    exemplar = emprestimo.exemplar
    regras = REGRAS_POR_CATEGORIA[usuario.categoria]

    emprestimo.data_devolucao = now
    emprestimo.estado = EstadoEmprestimo.DEVOLVIDO

    # Calcula dias de atraso (dias corridos)
    dias_atraso = (now.date() - emprestimo.data_prevista.date()).days
    if dias_atraso < 0:
        dias_atraso = 0

    # Regra 7: Devolução de exemplar com mais de 60 dias de atraso
    # marca o exemplar como baixado e gera multa no valor do teto da categoria.
    if dias_atraso > 60:
        exemplar.estado = EstadoExemplar.BAIXADO

        multa = Multa(
            emprestimo_id=emprestimo.id,
            valor=regras.teto_multa,
            estado=EstadoMulta.ABERTA,
            data_geracao=now,
        )
        db.add(multa)

        # Regra 2: atraso superior a 15 dias suspende usuário pelo dobro dos dias de atraso
        usuario.situacao = SituacaoUsuario.SUSPENSO
        nova_suspensao = now + timedelta(days=2 * dias_atraso)
        if usuario.suspenso_ate is None or nova_suspensao > usuario.suspenso_ate:
            usuario.suspenso_ate = nova_suspensao

        # Regra 6: se o último exemplar viável for baixado, cancela reservas
        cancelar_reservas_se_sem_exemplar_ativo(db, exemplar.livro_id)

    elif dias_atraso > 0:
        # Regra 5: Multa acumula por dia corrido de atraso, limitada ao teto.
        # Multa de professor é perdoada automaticamente se o atraso for de até 2 dias.
        if usuario.categoria == CategoriaUsuario.PROFESSOR and dias_atraso <= 2:
            valor_multa = round(Decimal(str(dias_atraso)) * regras.multa_por_dia, 2)
            multa = Multa(
                emprestimo_id=emprestimo.id,
                valor=valor_multa,
                estado=EstadoMulta.PERDOADA,
                data_geracao=now,
            )
            db.add(multa)
        else:
            valor_calculado = Decimal(str(dias_atraso)) * regras.multa_por_dia
            valor_multa = min(valor_calculado, regras.teto_multa)
            multa = Multa(
                emprestimo_id=emprestimo.id,
                valor=valor_multa,
                estado=EstadoMulta.ABERTA,
                data_geracao=now,
            )
            db.add(multa)

        # Regra 2: Atraso superior a 15 dias suspende o usuário pelo dobro dos dias de atraso
        if dias_atraso > 15:
            usuario.situacao = SituacaoUsuario.SUSPENSO
            nova_suspensao = now + timedelta(days=2 * dias_atraso)
            if usuario.suspenso_ate is None or nova_suspensao > usuario.suspenso_ate:
                usuario.suspenso_ate = nova_suspensao

    # Se o exemplar não foi baixado, gerenciar fila de reservas (Regra 4)
    if exemplar.estado != EstadoExemplar.BAIXADO:
        primeira_reserva = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == exemplar.livro_id,
                Reserva.estado == EstadoReserva.AGUARDANDO,
            )
            .order_by(Reserva.posicao_fila.asc(), Reserva.data_reserva.asc())
            .first()
        )
        if primeira_reserva:
            # Regra 4: o primeiro da fila passa ao estado disponível e tem 48 horas para retirá-lo
            primeira_reserva.estado = EstadoReserva.DISPONIVEL
            primeira_reserva.data_disponibilizacao = now
            primeira_reserva.posicao_fila = 0
            primeira_reserva.exemplar_id = exemplar.id
            exemplar.estado = EstadoExemplar.RESERVADO
            db.flush()
            reorganizar_fila(db, exemplar.livro_id)
        else:
            exemplar.estado = EstadoExemplar.DISPONIVEL

    db.commit()
    db.refresh(emprestimo)
    return emprestimo


def listar_emprestimos_por_usuario(db: Session, usuario_id: int) -> list[Emprestimo]:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {usuario_id} não encontrado.",
        )
    atualizar_emprestimos_atrasados(db)
    return (
        db.query(Emprestimo)
        .filter(Emprestimo.usuario_id == usuario_id)
        .order_by(Emprestimo.data_retirada.desc())
        .all()
    )


def listar_todos_emprestimos(
    db: Session,
    estado: EstadoEmprestimo | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Emprestimo]:
    atualizar_emprestimos_atrasados(db)
    query = db.query(Emprestimo)
    if estado:
        query = query.filter(Emprestimo.estado == estado)
    return query.order_by(Emprestimo.data_retirada.desc()).offset(skip).limit(limit).all()
