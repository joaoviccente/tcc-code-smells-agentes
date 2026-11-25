from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.config import (
    REGRAS_CATEGORIA,
    HORAS_LIMITE_RETIRADA_RESERVA,
    DIAS_LIMITE_SUSPENSAO_AUTOMATICA,
    FATOR_DURACAO_SUSPENSAO,
    DIAS_LIMITE_BAIXA_POR_ATRASO,
    DIAS_TOLERANCIA_PROFESSOR_PERDAO,
)
from app.models import Emprestimo, Exemplar, Usuario, Reserva, Multa
from app.models.enums import (
    CategoriaUsuario,
    EstadoEmprestimo,
    EstadoExemplar,
    SituacaoUsuario,
    EstadoReserva,
    EstadoMulta,
)
from app.schemas.emprestimo import EmprestimoCreate, EmprestimoDevolucao
from app.services.usuario_service import verificar_e_atualizar_situacao
from app.services.reserva_service import (
    processar_reservas_expiradas,
    reorganizar_fila,
)
from app.services.exemplar_service import verificar_cancelamento_reservas_apos_baixa
from app.utils import get_utcnow


def create_emprestimo(db: Session, emprestimo_in: EmprestimoCreate) -> Emprestimo:
    now = emprestimo_in.data_retirada or get_utcnow()
    processar_reservas_expiradas(db, now=now)

    usuario = db.query(Usuario).filter(Usuario.id == emprestimo_in.usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {emprestimo_in.usuario_id} não encontrado."
        )

    verificar_e_atualizar_situacao(db, usuario, now=now)

    # Regra 1: Empréstimo só é permitido a usuário ativo
    if usuario.situacao != SituacaoUsuario.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo não permitido: usuário está suspenso."
        )

    # Regra 1: Sem multa aberta
    multas_abertas = db.query(Multa).join(Emprestimo).filter(
        Emprestimo.usuario_id == usuario.id,
        Multa.estado == EstadoMulta.ABERTA
    ).count()
    if multas_abertas > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo não permitido: usuário possui multa(s) em aberto."
        )

    # Regra 1: Abaixo do seu limite de exemplares
    regra = REGRAS_CATEGORIA[usuario.categoria.value]
    emprestimos_ativos = db.query(Emprestimo).filter(
        Emprestimo.usuario_id == usuario.id,
        Emprestimo.data_devolucao.is_(None)
    ).count()
    if emprestimos_ativos >= regra.limite_exemplares:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Limite de empréstimos atingido para a categoria '{usuario.categoria.value}' (máximo {regra.limite_exemplares})."
        )

    exemplar = db.query(Exemplar).filter(Exemplar.id == emprestimo_in.exemplar_id).first()
    if not exemplar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exemplar com ID {emprestimo_in.exemplar_id} não encontrado."
        )

    # Regra 6: Exemplar em reparo ou baixado não pode ser emprestado
    if exemplar.estado in [EstadoExemplar.EM_REPARO, EstadoExemplar.BAIXADO]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exemplar não pode ser emprestado pois está no estado '{exemplar.estado.value}'."
        )

    if exemplar.estado == EstadoExemplar.EMPRESTADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exemplar já está emprestado."
        )

    # Verificar se o exemplar está reservado para outro usuário
    reserva_do_usuario = None
    if exemplar.estado == EstadoExemplar.RESERVADO:
        reserva_do_usuario = db.query(Reserva).filter(
            Reserva.livro_id == exemplar.livro_id,
            Reserva.usuario_id == usuario.id,
            Reserva.estado == EstadoReserva.DISPONIVEL
        ).first()

        if not reserva_do_usuario:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Exemplar está reservado para outro usuário."
            )
    else:
        # Se o exemplar estava disponivel, verificar se o usuario tinha reserva
        reserva_do_usuario = db.query(Reserva).filter(
            Reserva.livro_id == exemplar.livro_id,
            Reserva.usuario_id == usuario.id,
            Reserva.estado.in_([EstadoReserva.DISPONIVEL, EstadoReserva.AGUARDANDO])
        ).first()

    # Consumir a reserva caso o usuário possua
    if reserva_do_usuario:
        db.delete(reserva_do_usuario)
        reorganizar_fila(db, exemplar.livro_id)

    data_prevista = now + timedelta(days=regra.prazo_dias)

    db_emprestimo = Emprestimo(
        exemplar_id=exemplar.id,
        usuario_id=usuario.id,
        data_retirada=now,
        data_prevista=data_prevista,
        data_devolucao=None,
        estado=EstadoEmprestimo.ATIVO,
        numero_renovacoes=0,
    )
    exemplar.estado = EstadoExemplar.EMPRESTADO

    db.add(db_emprestimo)
    db.commit()
    db.refresh(db_emprestimo)
    return db_emprestimo


def renovar_emprestimo(db: Session, emprestimo_id: int) -> Emprestimo:
    now = get_utcnow()
    processar_reservas_expiradas(db, now=now)

    emprestimo = db.query(Emprestimo).filter(Emprestimo.id == emprestimo_id).first()
    if not emprestimo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Empréstimo com ID {emprestimo_id} não encontrado."
        )

    if emprestimo.data_devolucao is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível renovar empréstimo já devolvido."
        )

    # Regra 3: A renovação é negada se o empréstimo estiver atrasado
    if now > emprestimo.data_prevista or emprestimo.estado == EstadoEmprestimo.ATRASADO:
        emprestimo.estado = EstadoEmprestimo.ATRASADO
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação negada: o empréstimo está atrasado."
        )

    # Regra 3: A renovação é negada se houver fila de reserva para aquele livro
    fila_reservas = db.query(Reserva).filter(
        Reserva.livro_id == emprestimo.exemplar.livro_id,
        Reserva.estado.in_([EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL])
    ).count()
    if fila_reservas > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação negada: há reservas na fila para este livro."
        )

    # Regra 3: A renovação é negada se o limite de renovações da categoria já tiver sido atingido
    usuario = emprestimo.usuario
    regra = REGRAS_CATEGORIA[usuario.categoria.value]
    if emprestimo.numero_renovacoes >= regra.max_renovacoes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Renovação negada: limite de renovações atingido para a categoria '{usuario.categoria.value}' (máximo {regra.max_renovacoes})."
        )

    # Renova estendendo o prazo original a partir da data prevista anterior
    emprestimo.numero_renovacoes += 1
    emprestimo.data_prevista = emprestimo.data_prevista + timedelta(days=regra.prazo_dias)

    db.commit()
    db.refresh(emprestimo)
    return emprestimo


def devolver_emprestimo(
    db: Session,
    emprestimo_id: int,
    devolucao_in: Optional[EmprestimoDevolucao] = None
) -> Emprestimo:
    emprestimo = db.query(Emprestimo).filter(Emprestimo.id == emprestimo_id).first()
    if not emprestimo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Empréstimo com ID {emprestimo_id} não encontrado."
        )

    if emprestimo.data_devolucao is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este empréstimo já foi devolvido anteriormente."
        )

    data_devolucao = (
        devolucao_in.data_devolucao if devolucao_in and devolucao_in.data_devolucao
        else get_utcnow()
    )

    processar_reservas_expiradas(db, now=data_devolucao)

    emprestimo.data_devolucao = data_devolucao
    emprestimo.estado = EstadoEmprestimo.DEVOLVIDO

    exemplar = emprestimo.exemplar
    usuario = emprestimo.usuario
    regra = REGRAS_CATEGORIA[usuario.categoria.value]

    # Calcular dias corridos de atraso
    dias_atraso = 0
    if data_devolucao > emprestimo.data_prevista:
        dias_atraso = (data_devolucao.date() - emprestimo.data_prevista.date()).days

    # Regra 7: Devolução com mais de 60 dias de atraso marca exemplar como baixado e gera multa no teto
    if dias_atraso > DIAS_LIMITE_BAIXA_POR_ATRASO:
        exemplar.estado = EstadoExemplar.BAIXADO
        multa = Multa(
            emprestimo_id=emprestimo.id,
            valor=regra.teto_multa,
            estado=EstadoMulta.ABERTA,
            data_geracao=data_devolucao,
        )
        db.add(multa)

        # Regra 2: Atraso > 15 dias gera suspensão pelo dobro dos dias de atraso
        suspensao_dias = dias_atraso * FATOR_DURACAO_SUSPENSAO
        usuario.situacao = SituacaoUsuario.SUSPENSO
        fim_suspensao = data_devolucao + timedelta(days=suspensao_dias)
        if usuario.data_suspensao_fim is None or fim_suspensao > usuario.data_suspensao_fim:
            usuario.data_suspensao_fim = fim_suspensao

        db.commit()
        verificar_cancelamento_reservas_apos_baixa(db, exemplar.livro_id)

    elif dias_atraso > 0:
        # Regra 5: Multa acumula por dia corrido de atraso, limitada ao teto.
        # Multa de professor é perdoada automaticamente se o atraso for de até 2 dias.
        if usuario.categoria == CategoriaUsuario.PROFESSOR and dias_atraso <= DIAS_TOLERANCIA_PROFESSOR_PERDAO:
            valor_multa = round(Decimal(dias_atraso) * regra.multa_diaria, 2)
            estado_multa = EstadoMulta.PERDOADA
        else:
            valor_calculado = round(Decimal(dias_atraso) * regra.multa_diaria, 2)
            valor_multa = min(valor_calculado, regra.teto_multa)
            estado_multa = EstadoMulta.ABERTA

        multa = Multa(
            emprestimo_id=emprestimo.id,
            valor=valor_multa,
            estado=estado_multa,
            data_geracao=data_devolucao,
        )
        db.add(multa)

        # Regra 2: Atraso > 15 dias suspende pelo dobro dos dias de atraso
        if dias_atraso > DIAS_LIMITE_SUSPENSAO_AUTOMATICA:
            suspensao_dias = dias_atraso * FATOR_DURACAO_SUSPENSAO
            usuario.situacao = SituacaoUsuario.SUSPENSO
            fim_suspensao = data_devolucao + timedelta(days=suspensao_dias)
            if usuario.data_suspensao_fim is None or fim_suspensao > usuario.data_suspensao_fim:
                usuario.data_suspensao_fim = fim_suspensao

    # Se o exemplar não foi baixado, verificar fila de reservas (Regra 4)
    if exemplar.estado != EstadoExemplar.BAIXADO:
        primeira_reserva = db.query(Reserva).filter(
            Reserva.livro_id == exemplar.livro_id,
            Reserva.estado == EstadoReserva.AGUARDANDO
        ).order_by(Reserva.data.asc()).first()

        if primeira_reserva:
            primeira_reserva.estado = EstadoReserva.DISPONIVEL
            primeira_reserva.data_limite_retirada = data_devolucao + timedelta(hours=HORAS_LIMITE_RETIRADA_RESERVA)
            primeira_reserva.exemplar_id = exemplar.id
            exemplar.estado = EstadoExemplar.RESERVADO
            reorganizar_fila(db, exemplar.livro_id)
        else:
            exemplar.estado = EstadoExemplar.DISPONIVEL

    db.commit()
    db.refresh(emprestimo)
    return emprestimo


def get_emprestimos_por_usuario(
    db: Session,
    usuario_id: int,
    apenas_ativos: bool = False
) -> List[Emprestimo]:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {usuario_id} não encontrado."
        )

    verificar_e_atualizar_situacao(db, usuario)

    query = db.query(Emprestimo).filter(Emprestimo.usuario_id == usuario_id)
    if apenas_ativos:
        query = query.filter(Emprestimo.data_devolucao.is_(None))
    return query.order_by(Emprestimo.data_retirada.desc()).all()


def get_emprestimo_by_id(db: Session, emprestimo_id: int) -> Emprestimo:
    emprestimo = db.query(Emprestimo).filter(Emprestimo.id == emprestimo_id).first()
    if not emprestimo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Empréstimo com ID {emprestimo_id} não encontrado."
        )
    return emprestimo


def get_emprestimos(
    db: Session,
    usuario_id: Optional[int] = None,
    exemplar_id: Optional[int] = None,
    estado: Optional[EstadoEmprestimo] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Emprestimo]:
    query = db.query(Emprestimo)
    if usuario_id:
        query = query.filter(Emprestimo.usuario_id == usuario_id)
    if exemplar_id:
        query = query.filter(Emprestimo.exemplar_id == exemplar_id)
    if estado:
        query = query.filter(Emprestimo.estado == estado)
    return query.order_by(Emprestimo.data_retirada.desc()).offset(skip).limit(limit).all()
