from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.emprestimo import Emprestimo
from app.models.enums import (
    CategoriaUsuario,
    EstadoEmprestimo,
    EstadoExemplar,
    EstadoMulta,
    EstadoReserva,
    SituacaoUsuario,
)
from app.models.exemplar import Exemplar
from app.models.multa import Multa
from app.models.reserva import Reserva
from app.models.usuario import Usuario
from app.schemas.emprestimo import EmprestimoCreate, EmprestimoDevolver, EmprestimoRenovar
from app.services.exemplar_service import verificar_cancelamento_reservas_por_baixa
from app.services.regras import (
    DIAS_ATRASO_SUSPENSAO,
    DIAS_LIMITE_BAIXA,
    DIAS_PERDAO_PROFESSOR,
    FATOR_SUSPENSAO,
    HORAS_EXPIRACAO_RESERVA,
    REGRAS_CATEGORIA,
)
from app.services.reserva_service import (
    processar_expiracoes,
    reordenar_fila_aguardando,
)
from app.services.usuario_service import (
    atualizar_situacao_usuario,
    calcular_dias_atraso,
)


def create_emprestimo(db: Session, emp_in: EmprestimoCreate) -> Emprestimo:
    data_retirada = emp_in.data_retirada or datetime.now(timezone.utc)
    if data_retirada.tzinfo is None:
        data_retirada = data_retirada.replace(tzinfo=timezone.utc)

    # Processar expirações de reservas pendentes
    processar_expiracoes(db, data_retirada)

    # 1. Validar usuário
    usuario = db.query(Usuario).filter(Usuario.id == emp_in.usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {emp_in.usuario_id} não encontrado.",
        )

    atualizar_situacao_usuario(db, usuario, data_retirada)

    # Regra 1: Usuário deve estar ativo
    if usuario.situacao != SituacaoUsuario.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo negado: usuário suspenso ou inativo.",
        )

    # Regra 1: Usuário sem multa aberta
    tem_multa_aberta = (
        db.query(Multa)
        .join(Emprestimo, Multa.emprestimo_id == Emprestimo.id)
        .filter(
            Emprestimo.usuario_id == usuario.id,
            Multa.estado == EstadoMulta.ABERTA,
        )
        .first()
    )
    if tem_multa_aberta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo negado: usuário possui multa aberta.",
        )

    # Regra 1: Usuário abaixo do seu limite de exemplares
    regras = REGRAS_CATEGORIA[usuario.categoria]
    limite_exemplares = regras["limite_exemplares"]
    qtd_emprestimos_ativos = (
        db.query(Emprestimo)
        .filter(
            Emprestimo.usuario_id == usuario.id,
            Emprestimo.estado.in_([EstadoEmprestimo.ATIVO, EstadoEmprestimo.ATRASADO]),
        )
        .count()
    )
    if qtd_emprestimos_ativos >= limite_exemplares:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Empréstimo negado: limite de {limite_exemplares} exemplar(es) para categoria {usuario.categoria.value} atingido.",
        )

    # 2. Validar exemplar
    exemplar = db.query(Exemplar).filter(Exemplar.id == emp_in.exemplar_id).first()
    if not exemplar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exemplar com ID {emp_in.exemplar_id} não encontrado.",
        )

    # Regra 6: Exemplar em reparo ou baixado não pode ser emprestado nem reservado
    if exemplar.estado in [EstadoExemplar.EM_REPARO, EstadoExemplar.BAIXADO]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Empréstimo negado: exemplar está em estado '{exemplar.estado.value}'.",
        )

    if exemplar.estado == EstadoExemplar.EMPRESTADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo negado: exemplar já está emprestado.",
        )

    # Se estiver reservado, verificar se a reserva é deste usuário
    if exemplar.estado == EstadoExemplar.RESERVADO:
        reserva_disp = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == exemplar.livro_id,
                Reserva.estado == EstadoReserva.DISPONIVEL,
            )
            .first()
        )
        if reserva_disp:
            if reserva_disp.usuario_id != usuario.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Empréstimo negado: exemplar reservado para outro usuário.",
                )
            # Usuário que reservou está retirando: consumir a reserva
            db.delete(reserva_disp)
            reordenar_fila_aguardando(db, exemplar.livro_id)
    else:
        # Exemplar disponível: verificar se há fila de reserva com prioridade
        reserva_disp = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == exemplar.livro_id,
                Reserva.estado == EstadoReserva.DISPONIVEL,
            )
            .first()
        )
        if reserva_disp and reserva_disp.usuario_id != usuario.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empréstimo negado: exemplar reservado para outro usuário da fila.",
            )

        # Se houver alguém na fila aguardando e o usuário for o primeiro
        primeira_aguardando = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == exemplar.livro_id,
                Reserva.estado == EstadoReserva.AGUARDANDO,
            )
            .order_by(Reserva.posicao_fila.asc(), Reserva.data.asc())
            .first()
        )
        if primeira_aguardando:
            if primeira_aguardando.usuario_id == usuario.id:
                # O usuário que estava esperando está pegando
                db.delete(primeira_aguardando)
                reordenar_fila_aguardando(db, exemplar.livro_id)
            elif not reserva_disp:
                # Há alguém esperando e não é esse usuário
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Empréstimo negado: existe fila de reserva para este livro.",
                )

    prazo_dias = regras["prazo_dias"]
    data_prevista = data_retirada + timedelta(days=prazo_dias)

    exemplar.estado = EstadoExemplar.EMPRESTADO

    emprestimo = Emprestimo(
        exemplar_id=exemplar.id,
        usuario_id=usuario.id,
        data_retirada=data_retirada,
        data_prevista=data_prevista,
        estado=EstadoEmprestimo.ATIVO,
        numero_renovacoes=0,
    )
    db.add(emprestimo)
    db.commit()
    db.refresh(emprestimo)
    return emprestimo


def renovar_emprestimo(
    db: Session, emprestimo_id: int, renovar_in: Optional[EmprestimoRenovar] = None
) -> Emprestimo:
    data_renovacao = (
        renovar_in.data_renovacao
        if renovar_in and renovar_in.data_renovacao
        else datetime.now(timezone.utc)
    )
    if data_renovacao.tzinfo is None:
        data_renovacao = data_renovacao.replace(tzinfo=timezone.utc)

    processar_expiracoes(db, data_renovacao)

    emprestimo = db.query(Emprestimo).filter(Emprestimo.id == emprestimo_id).first()
    if not emprestimo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Empréstimo com ID {emprestimo_id} não encontrado.",
        )

    if emprestimo.estado == EstadoEmprestimo.DEVOLVIDO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível renovar um empréstimo já devolvido.",
        )

    usuario = emprestimo.usuario
    atualizar_situacao_usuario(db, usuario, data_renovacao)

    if usuario.situacao != SituacaoUsuario.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação negada: usuário suspenso.",
        )

    # Regra 3: Negada se o empréstimo estiver atrasado
    prevista = (
        emprestimo.data_prevista
        if emprestimo.data_prevista.tzinfo
        else emprestimo.data_prevista.replace(tzinfo=timezone.utc)
    )
    if emprestimo.estado == EstadoEmprestimo.ATRASADO or data_renovacao > prevista:
        emprestimo.estado = EstadoEmprestimo.ATRASADO
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação negada: o empréstimo está atrasado.",
        )

    # Regra 3: Negada se o limite de renovações da categoria já tiver sido atingido
    regras = REGRAS_CATEGORIA[usuario.categoria]
    limite_renovacoes = regras["limite_renovacoes"]
    if emprestimo.numero_renovacoes >= limite_renovacoes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Renovação negada: limite de {limite_renovacoes} renovações da categoria {usuario.categoria.value} atingido.",
        )

    # Regra 3: Negada se houver fila de reserva para aquele livro
    tem_fila_reserva = (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == emprestimo.exemplar.livro_id,
            Reserva.estado.in_([EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL]),
        )
        .first()
    )
    if tem_fila_reserva:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação negada: existe fila de reserva para este livro.",
        )

    prazo_dias = regras["prazo_dias"]
    emprestimo.numero_renovacoes += 1
    emprestimo.data_prevista = prevista + timedelta(days=prazo_dias)

    db.commit()
    db.refresh(emprestimo)
    return emprestimo


def devolver_emprestimo(
    db: Session, emprestimo_id: int, devolver_in: Optional[EmprestimoDevolver] = None
) -> Emprestimo:
    data_devolucao = (
        devolver_in.data_devolucao
        if devolver_in and devolver_in.data_devolucao
        else datetime.now(timezone.utc)
    )
    if data_devolucao.tzinfo is None:
        data_devolucao = data_devolucao.replace(tzinfo=timezone.utc)

    processar_expiracoes(db, data_devolucao)

    emprestimo = db.query(Emprestimo).filter(Emprestimo.id == emprestimo_id).first()
    if not emprestimo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Empréstimo com ID {emprestimo_id} não encontrado.",
        )

    if emprestimo.estado == EstadoEmprestimo.DEVOLVIDO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo já foi devolvido.",
        )

    usuario = emprestimo.usuario
    exemplar = emprestimo.exemplar
    regras = REGRAS_CATEGORIA[usuario.categoria]

    emprestimo.data_devolucao = data_devolucao
    emprestimo.estado = EstadoEmprestimo.DEVOLVIDO

    prevista = (
        emprestimo.data_prevista
        if emprestimo.data_prevista.tzinfo
        else emprestimo.data_prevista.replace(tzinfo=timezone.utc)
    )
    dias_atraso = calcular_dias_atraso(data_devolucao, prevista)

    # Regra 7: Devolução com mais de 60 dias de atraso marca exemplar como baixado e gera multa no teto
    if dias_atraso > DIAS_LIMITE_BAIXA:
        exemplar.estado = EstadoExemplar.BAIXADO
        db.flush()
        multa = Multa(
            emprestimo_id=emprestimo.id,
            valor=regras["teto_multa"],
            estado=EstadoMulta.ABERTA,
            data_geracao=data_devolucao,
        )
        db.add(multa)

        # Regra 2: Usuário suspenso pelo dobro dos dias de atraso
        usuario.situacao = SituacaoUsuario.SUSPENSO
        dias_suspensao = FATOR_SUSPENSAO * dias_atraso
        fim_suspensao = data_devolucao + timedelta(days=dias_suspensao)
        if not usuario.data_fim_suspensao or fim_suspensao > (
            usuario.data_fim_suspensao
            if usuario.data_fim_suspensao.tzinfo
            else usuario.data_fim_suspensao.replace(tzinfo=timezone.utc)
        ):
            usuario.data_fim_suspensao = fim_suspensao

        # Regra 6: se o último exemplar disponível for baixado, cancelar todas as reservas
        verificar_cancelamento_reservas_por_baixa(db, exemplar.livro_id)

    elif dias_atraso > 0:
        # Regra 5: Multa acumula por dia corrido de atraso, limitada ao teto.
        # Multa de professor é perdoada automaticamente se atraso for de até 2 dias.
        valor_calculado = Decimal(str(dias_atraso)) * regras["multa_diaria"]
        valor_final = min(valor_calculado, regras["teto_multa"])

        if usuario.categoria == CategoriaUsuario.PROFESSOR and dias_atraso <= DIAS_PERDAO_PROFESSOR:
            multa = Multa(
                emprestimo_id=emprestimo.id,
                valor=valor_calculado,
                estado=EstadoMulta.PERDOADA,
                data_geracao=data_devolucao,
            )
        else:
            multa = Multa(
                emprestimo_id=emprestimo.id,
                valor=valor_final,
                estado=EstadoMulta.ABERTA,
                data_geracao=data_devolucao,
            )
        db.add(multa)

        # Regra 2: Atraso superior a 15 dias suspende usuário pelo dobro dos dias
        if dias_atraso > DIAS_ATRASO_SUSPENSAO:
            usuario.situacao = SituacaoUsuario.SUSPENSO
            dias_suspensao = FATOR_SUSPENSAO * dias_atraso
            fim_suspensao = data_devolucao + timedelta(days=dias_suspensao)
            if not usuario.data_fim_suspensao or fim_suspensao > (
                usuario.data_fim_suspensao
                if usuario.data_fim_suspensao.tzinfo
                else usuario.data_fim_suspensao.replace(tzinfo=timezone.utc)
            ):
                usuario.data_fim_suspensao = fim_suspensao

    # Regra 4: Alocação para a fila de reserva ao devolver (caso exemplar não tenha sido baixado)
    if exemplar.estado != EstadoExemplar.BAIXADO:
        proxima_reserva = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == exemplar.livro_id,
                Reserva.estado == EstadoReserva.AGUARDANDO,
            )
            .order_by(Reserva.posicao_fila.asc(), Reserva.data.asc())
            .first()
        )
        if proxima_reserva:
            proxima_reserva.estado = EstadoReserva.DISPONIVEL
            proxima_reserva.data_disponibilizacao = data_devolucao
            proxima_reserva.data_limite_retirada = data_devolucao + timedelta(
                hours=HORAS_EXPIRACAO_RESERVA
            )
            proxima_reserva.posicao_fila = 1
            exemplar.estado = EstadoExemplar.RESERVADO
            reordenar_fila_aguardando(db, exemplar.livro_id)
        else:
            exemplar.estado = EstadoExemplar.DISPONIVEL

    db.commit()
    db.refresh(emprestimo)
    return emprestimo


def list_emprestimos_usuario(
    db: Session, usuario_id: int, data_referencia: Optional[datetime] = None
) -> List[Emprestimo]:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {usuario_id} não encontrado.",
        )
    atualizar_situacao_usuario(db, usuario, data_referencia)
    return (
        db.query(Emprestimo)
        .filter(Emprestimo.usuario_id == usuario_id)
        .order_by(Emprestimo.data_retirada.desc())
        .all()
    )


def list_emprestimos(
    db: Session,
    usuario_id: Optional[int] = None,
    exemplar_id: Optional[int] = None,
    estado: Optional[EstadoEmprestimo] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Emprestimo]:
    query = db.query(Emprestimo)
    if usuario_id is not None:
        query = query.filter(Emprestimo.usuario_id == usuario_id)
    if exemplar_id is not None:
        query = query.filter(Emprestimo.exemplar_id == exemplar_id)
    if estado is not None:
        query = query.filter(Emprestimo.estado == estado)
    return query.order_by(Emprestimo.data_retirada.desc()).offset(skip).limit(limit).all()


def get_emprestimo(db: Session, emprestimo_id: int) -> Emprestimo:
    emp = db.query(Emprestimo).filter(Emprestimo.id == emprestimo_id).first()
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Empréstimo com ID {emprestimo_id} não encontrado.",
        )
    return emp
