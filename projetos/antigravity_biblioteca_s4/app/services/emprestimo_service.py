from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.config import (
    REGRAS_CATEGORIA,
    HORAS_LIMITE_RETIRADA_RESERVA,
    DIAS_LIMITE_SUSPENSAO,
    MULTIPLICADOR_SUSPENSAO,
    DIAS_LIMITE_BAIXA_ATRASO,
    DIAS_TOLERANCIA_PROFESSOR,
)
from app.models.emprestimo import Emprestimo
from app.models.exemplar import Exemplar
from app.models.usuario import Usuario
from app.models.reserva import Reserva
from app.models.multa import Multa
from app.models.enums import (
    CategoriaUsuario,
    SituacaoUsuario,
    EstadoExemplar,
    EstadoEmprestimo,
    EstadoReserva,
    EstadoMulta,
)
from app.schemas.emprestimo import EmprestimoCreate
from app.services.usuario_service import check_e_atualizar_suspensao
from app.services.reserva_service import (
    processar_reservas_expiradas,
    reordenar_fila,
    cancelar_todas_reservas_do_livro,
)


def atualizar_estados_atrasados(db: Session, current_time: Optional[datetime] = None) -> None:
    """Atualiza o estado de empréstimos ativos cuja data prevista já passou."""
    agora = current_time or datetime.now()
    emprestimos_atrasados = (
        db.query(Emprestimo)
        .filter(
            Emprestimo.estado == EstadoEmprestimo.ATIVO,
            Emprestimo.data_devolucao.is_(None),
            Emprestimo.data_prevista < agora,
        )
        .all()
    )
    for emp in emprestimos_atrasados:
        emp.estado = EstadoEmprestimo.ATRASADO
    db.commit()


def get_emprestimos(
    db: Session,
    usuario_id: Optional[int] = None,
    exemplar_id: Optional[int] = None,
    estado: Optional[EstadoEmprestimo] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Emprestimo]:
    atualizar_estados_atrasados(db)
    query = db.query(Emprestimo)
    if usuario_id:
        query = query.filter(Emprestimo.usuario_id == usuario_id)
    if exemplar_id:
        query = query.filter(Emprestimo.exemplar_id == exemplar_id)
    if estado:
        query = query.filter(Emprestimo.estado == estado)
    return query.order_by(Emprestimo.data_retirada.desc()).offset(skip).limit(limit).all()


def get_emprestimo_by_id(db: Session, emprestimo_id: int) -> Emprestimo:
    atualizar_estados_atrasados(db)
    emprestimo = db.query(Emprestimo).filter(Emprestimo.id == emprestimo_id).first()
    if not emprestimo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Empréstimo com ID {emprestimo_id} não encontrado.",
        )
    return emprestimo


def create_emprestimo(db: Session, emprestimo_in: EmprestimoCreate) -> Emprestimo:
    agora = emprestimo_in.data_retirada or datetime.now()
    atualizar_estados_atrasados(db, agora)
    processar_reservas_expiradas(db, agora)

    # 1. Validar usuário
    usuario = db.query(Usuario).filter(Usuario.id == emprestimo_in.usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {emprestimo_in.usuario_id} não encontrado.",
        )
    check_e_atualizar_suspensao(usuario, agora)

    # Regra 2: "Usuário com atraso superior a 15 dias em qualquer empréstimo é automaticamente suspenso"
    # Verificar se o usuário possui empréstimo com atraso > 15 dias
    emprestimos_do_usuario = (
        db.query(Emprestimo)
        .filter(
            Emprestimo.usuario_id == usuario.id,
            Emprestimo.data_devolucao.is_(None),
            Emprestimo.data_prevista < agora,
        )
        .all()
    )
    for emp in emprestimos_do_usuario:
        dias_atraso = (agora.date() - emp.data_prevista.date()).days
        if dias_atraso > DIAS_LIMITE_SUSPENSAO:
            usuario.situacao = SituacaoUsuario.SUSPENSO
            dias_susp = MULTIPLICADOR_SUSPENSAO * dias_atraso
            fim_susp = agora + timedelta(days=dias_susp)
            if not usuario.data_fim_suspensao or fim_susp > usuario.data_fim_suspensao:
                usuario.data_fim_suspensao = fim_susp
            db.commit()
            break

    # Regra 1: "Empréstimo só é permitido a usuário ativo"
    if usuario.situacao == SituacaoUsuario.SUSPENSO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo não permitido: usuário está suspenso.",
        )

    # Regra 1: "sem multa aberta"
    multa_aberta = (
        db.query(Multa)
        .join(Emprestimo)
        .filter(
            Emprestimo.usuario_id == usuario.id,
            Multa.estado == EstadoMulta.ABERTA,
        )
        .first()
    )
    if multa_aberta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo não permitido: usuário possui multas em aberto pendentes de pagamento.",
        )

    # Regra 1: "e abaixo do seu limite de exemplares"
    regras = REGRAS_CATEGORIA[usuario.categoria]
    total_ativos = (
        db.query(Emprestimo)
        .filter(
            Emprestimo.usuario_id == usuario.id,
            Emprestimo.estado.in_([EstadoEmprestimo.ATIVO, EstadoEmprestimo.ATRASADO]),
        )
        .count()
    )
    if total_ativos >= regras.limite_exemplares:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Empréstimo não permitido: limite de {regras.limite_exemplares} exemplares atingido para a categoria {usuario.categoria.value}.",
        )

    # 2. Validar exemplar
    exemplar = db.query(Exemplar).filter(Exemplar.id == emprestimo_in.exemplar_id).first()
    if not exemplar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exemplar com ID {emprestimo_in.exemplar_id} não encontrado.",
        )

    # Regra 6: "Exemplar em reparo ou baixado não pode ser emprestado nem reservado"
    if exemplar.estado == EstadoExemplar.EM_REPARO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo não permitido: exemplar está em reparo.",
        )
    if exemplar.estado == EstadoExemplar.BAIXADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo não permitido: exemplar está baixado.",
        )
    if exemplar.estado == EstadoExemplar.EMPRESTADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo não permitido: exemplar já está emprestado.",
        )

    # Se o exemplar estiver reservado, verificar se está reservado especificamente para este usuário
    if exemplar.estado == EstadoExemplar.RESERVADO:
        reserva_do_usuario = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == exemplar.livro_id,
                Reserva.usuario_id == usuario.id,
                Reserva.estado == EstadoReserva.DISPONIVEL,
            )
            .first()
        )
        if not reserva_do_usuario:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empréstimo não permitido: exemplar está reservado para outro usuário.",
            )
        # Finaliza a reserva atendida
        reserva_do_usuario.estado = EstadoReserva.CONCLUIDA
        reserva_do_usuario.posicao_na_fila = None
    else:
        # Se estava DISPONÍVEL, e o próprio usuário tinha reserva ativa para o livro, conclui a reserva
        reserva_usuario = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == exemplar.livro_id,
                Reserva.usuario_id == usuario.id,
                Reserva.estado.in_([EstadoReserva.DISPONIVEL, EstadoReserva.AGUARDANDO]),
            )
            .first()
        )
        if reserva_usuario:
            reserva_usuario.estado = EstadoReserva.CONCLUIDA
            reserva_usuario.posicao_na_fila = None
            reordenar_fila(db, exemplar.livro_id)

    # Criação do empréstimo
    data_prevista = agora + timedelta(days=regras.prazo_dias)
    novo_emprestimo = Emprestimo(
        exemplar_id=exemplar.id,
        usuario_id=usuario.id,
        data_retirada=agora,
        data_prevista=data_prevista,
        data_devolucao=None,
        estado=EstadoEmprestimo.ATIVO,
        numero_de_renovacoes=0,
    )
    exemplar.estado = EstadoExemplar.EMPRESTADO

    db.add(novo_emprestimo)
    db.commit()
    db.refresh(novo_emprestimo)
    return novo_emprestimo


def renovar_emprestimo(
    db: Session, emprestimo_id: int, data_renovacao: Optional[datetime] = None
) -> Emprestimo:
    agora = data_renovacao or datetime.now()
    atualizar_estados_atrasados(db, agora)
    processar_reservas_expiradas(db, agora)

    emprestimo = get_emprestimo_by_id(db, emprestimo_id)
    if emprestimo.data_devolucao is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação não permitida: empréstimo já foi devolvido.",
        )

    usuario = emprestimo.usuario
    regras = REGRAS_CATEGORIA[usuario.categoria]

    # Regra 3: "A renovação é negada se houver fila de reserva para aquele livro,
    # se o empréstimo estiver atrasado ou se o limite de renovações da categoria já tiver sido atingido."

    # 1. Checar se o empréstimo está atrasado
    if emprestimo.estado == EstadoEmprestimo.ATRASADO or agora > emprestimo.data_prevista:
        emprestimo.estado = EstadoEmprestimo.ATRASADO
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação negada: empréstimo em atraso.",
        )

    # 2. Checar limite de renovações
    if emprestimo.numero_de_renovacoes >= regras.max_renovacoes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Renovação negada: limite de {regras.max_renovacoes} renovações atingido para a categoria {usuario.categoria.value}.",
        )

    # 3. Checar fila de reserva para aquele livro
    tem_fila = (
        db.query(Reserva)
        .filter(
            Reserva.livro_id == emprestimo.exemplar.livro_id,
            Reserva.estado.in_([EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL]),
        )
        .count()
    ) > 0
    if tem_fila:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação negada: há fila de reserva para aquele livro.",
        )

    # Realizar renovação
    emprestimo.numero_de_renovacoes += 1
    emprestimo.data_prevista = emprestimo.data_prevista + timedelta(days=regras.prazo_dias)

    db.commit()
    db.refresh(emprestimo)
    return emprestimo


def devolver_emprestimo(
    db: Session, emprestimo_id: int, data_devolucao: Optional[datetime] = None
) -> Emprestimo:
    agora = data_devolucao or datetime.now()
    emprestimo = get_emprestimo_by_id(db, emprestimo_id)

    if emprestimo.data_devolucao is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Devolução não permitida: empréstimo já foi devolvido.",
        )

    usuario = emprestimo.usuario
    exemplar = emprestimo.exemplar
    regras = REGRAS_CATEGORIA[usuario.categoria]

    emprestimo.data_devolucao = agora
    emprestimo.estado = EstadoEmprestimo.DEVOLVIDO

    # Calcular dias corridos de atraso
    diff_dias = (agora.date() - emprestimo.data_prevista.date()).days
    dias_atraso = max(0, diff_dias)

    if dias_atraso > 0:
        # Regra 7: "Devolução de exemplar com mais de 60 dias de atraso marca o exemplar como baixado e gera multa no valor do teto da categoria."
        if dias_atraso > DIAS_LIMITE_BAIXA_ATRASO:
            exemplar.estado = EstadoExemplar.BAIXADO
            multa = Multa(
                emprestimo_id=emprestimo.id,
                valor=regras.teto_multa,
                estado=EstadoMulta.ABERTA,
            )
            db.add(multa)

            # Regra 6: se o último exemplar disponível de um livro for baixado, todas as reservas daquele livro são canceladas
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

        else:
            # Regra 5: "A multa acumula por dia corrido de atraso, conforme a categoria, limitada ao teto.
            # Multa de professor é perdoada automaticamente se o atraso for de até 2 dias."
            if usuario.categoria == CategoriaUsuario.PROFESSOR and dias_atraso <= DIAS_TOLERANCIA_PROFESSOR:
                valor_multa = round(dias_atraso * regras.multa_diaria, 2)
                estado_multa = EstadoMulta.PERDOADA
            else:
                valor_calc = round(dias_atraso * regras.multa_diaria, 2)
                valor_multa = min(valor_calc, regras.teto_multa)
                estado_multa = EstadoMulta.ABERTA

            multa = Multa(
                emprestimo_id=emprestimo.id,
                valor=valor_multa,
                estado=estado_multa,
            )
            db.add(multa)

        # Regra 2: "Usuário com atraso superior a 15 dias em qualquer empréstimo é automaticamente suspenso, e a suspensão dura o dobro dos dias de atraso."
        if dias_atraso > DIAS_LIMITE_SUSPENSAO:
            dias_suspensao = MULTIPLICADOR_SUSPENSAO * dias_atraso
            usuario.situacao = SituacaoUsuario.SUSPENSO
            usuario.data_fim_suspensao = agora + timedelta(days=dias_suspensao)

    # Se o exemplar não foi baixado pela regra 7
    if exemplar.estado != EstadoExemplar.BAIXADO:
        # Regra 4: "Quando um exemplar é devolvido, o primeiro da fila passa ao estado disponível e tem 48 horas para retirá-lo; esgotado o prazo, a reserva expira e a vez passa ao próximo."
        processar_reservas_expiradas(db, agora)
        primeira_reserva = (
            db.query(Reserva)
            .filter(
                Reserva.livro_id == exemplar.livro_id,
                Reserva.estado == EstadoReserva.AGUARDANDO,
            )
            .order_by(Reserva.posicao_na_fila.asc(), Reserva.data.asc())
            .first()
        )

        if primeira_reserva:
            primeira_reserva.estado = EstadoReserva.DISPONIVEL
            primeira_reserva.data_limite_retirada = agora + timedelta(hours=HORAS_LIMITE_RETIRADA_RESERVA)
            primeira_reserva.exemplar_id = exemplar.id
            exemplar.estado = EstadoExemplar.RESERVADO
            reordenar_fila(db, exemplar.livro_id)
        else:
            exemplar.estado = EstadoExemplar.DISPONIVEL

    db.commit()
    db.refresh(emprestimo)
    return emprestimo
