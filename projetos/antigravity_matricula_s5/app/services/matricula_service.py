from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status

from app.config import settings
from app.models.aluno import Aluno
from app.models.disciplina import Disciplina
from app.models.turma import Turma
from app.models.matricula import Matricula
from app.models.historico import Historico
from app.models.enums import (
    CategoriaAluno,
    SituacaoAluno,
    EstadoTurma,
    EstadoMatricula,
    SituacaoHistorico,
)
from app.services.schedule_service import check_schedule_conflict


def get_current_time(data_ref: Optional[datetime] = None) -> datetime:
    """Retorna data_ref ou o timestamp atual em UTC."""
    if data_ref is not None:
        if data_ref.tzinfo is None:
            return data_ref.replace(tzinfo=timezone.utc)
        return data_ref
    return datetime.now(timezone.utc)


def get_waitlist_ordered(db: Session, turma_id: int) -> List[Matricula]:
    """
    Retorna a fila de espera da turma ordenada por:
    1. Prioridade da categoria (pos: 1, graduacao: 2, especial: 3)
    2. Data da solicitação (ASC - mais antiga primeiro)
    """
    waitlist_items = (
        db.query(Matricula)
        .join(Aluno)
        .filter(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.LISTA_DE_ESPERA
        )
        .all()
    )

    # Ordena em Python usando a prioridade da categoria e a data
    waitlist_items.sort(
        key=lambda m: (m.aluno.categoria.prioridade_fila, m.data)
    )
    return waitlist_items


def processar_fila_espera(db: Session, turma_id: int, data_ref: Optional[datetime] = None) -> List[Matricula]:
    """
    Processa a lista de espera de uma turma:
    1. Cancela quem teve vaga liberada mas ultrapassou o prazo de 48 horas.
    2. Aloca vagas livres para os primeiros da fila, concedendo 48 horas para confirmação.
    3. Atualiza o estado da turma (aberta vs lotada).
    """
    now = get_current_time(data_ref)
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        return []

    # 1. Verificar matrículas com oferta expirada (48h)
    matriculas_em_espera = (
        db.query(Matricula)
        .filter(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.LISTA_DE_ESPERA,
            Matricula.limite_confirmacao_em.isnot(None),
        )
        .all()
    )

    for mat in matriculas_em_espera:
        limite = mat.limite_confirmacao_em
        if limite.tzinfo is None:
            limite = limite.replace(tzinfo=timezone.utc)
        if now > limite:
            # Esgotado o prazo de 48 horas: cancelada e passa ao próximo
            mat.estado = EstadoMatricula.CANCELADA
            mat.vaga_liberada_em = None
            mat.limite_confirmacao_em = None

    db.flush()

    # 2. Contar vagas ocupadas e reservadas
    confirmadas = (
        db.query(Matricula)
        .filter(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        )
        .count()
    )

    reservadas_ativas = (
        db.query(Matricula)
        .filter(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.LISTA_DE_ESPERA,
            Matricula.limite_confirmacao_em.isnot(None),
            Matricula.limite_confirmacao_em > now,
        )
        .count()
    )

    vagas_disponiveis = turma.numero_vagas - confirmadas - reservadas_ativas
    notificados: List[Matricula] = []

    if vagas_disponiveis > 0:
        # Buscar próximos da fila que ainda não foram notificados
        candidatos = get_waitlist_ordered(db, turma_id)
        for cand in candidatos:
            if cand.vaga_liberada_em is None and vagas_disponiveis > 0:
                cand.vaga_liberada_em = now
                cand.limite_confirmacao_em = now + timedelta(hours=settings.PRAZO_CONFIRMACAO_FILA_HORAS)
                vagas_disponiveis -= 1
                reservadas_ativas += 1
                notificados.append(cand)

    # 3. Atualizar estado da turma
    if confirmadas + reservadas_ativas >= turma.numero_vagas:
        if turma.estado == EstadoTurma.ABERTA:
            turma.estado = EstadoTurma.LOTADA
    else:
        if turma.estado == EstadoTurma.LOTADA:
            turma.estado = EstadoTurma.ABERTA

    db.commit()
    return notificados


def solicitar_matricula(
    db: Session,
    aluno_id: int,
    turma_id: int,
    auto_confirm: bool = True,
    data_ref: Optional[datetime] = None
) -> Matricula:
    """
    Processa a solicitação de matrícula aplicando as Regras 1, 2, 3 e 6.
    """
    now = get_current_time(data_ref)

    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {aluno_id} não encontrado."
        )

    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turma com ID {turma_id} não encontrada."
        )

    if turma.estado in (EstadoTurma.CANCELADA, EstadoTurma.ENCERRADA):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não é possível solicitar matrícula em turma com estado '{turma.estado.value}'."
        )

    # REGRA 1: Aluno deve estar ativo
    if aluno.situacao != SituacaoAluno.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Matrícula não permitida: aluno possui situação '{aluno.situacao.value}'. Apenas alunos ativos podem se matricular."
        )

    # REGRA 3: Três reprovações na mesma disciplina impedem nova matrícula
    reprovacoes = (
        db.query(Historico)
        .filter(
            Historico.aluno_id == aluno.id,
            Historico.disciplina_id == turma.disciplina_id,
            Historico.situacao.in_([SituacaoHistorico.REPROVADO, SituacaoHistorico.REPROVADO_POR_FALTA])
        )
        .count()
    )
    if reprovacoes >= settings.MAX_REPROVACOES_DISCIPLINA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Aluno reprovado {reprovacoes} vezes na disciplina '{turma.disciplina.nome}'. "
                f"Matrícula impedida conforme regra de negócio (máximo permitido: {settings.MAX_REPROVACOES_DISCIPLINA} reprovações)."
            )
        )

    # REGRA 1: Pré-requisitos cumpridos com aprovação no histórico
    for prereq in turma.disciplina.prerequisitos:
        aprovado = (
            db.query(Historico)
            .filter(
                Historico.aluno_id == aluno.id,
                Historico.disciplina_id == prereq.id,
                Historico.situacao == SituacaoHistorico.APROVADO
            )
            .first()
        )
        if not aprovado:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Pré-requisito não cumprido: disciplina '{prereq.nome}' ({prereq.codigo}) exige aprovação prévia no histórico."
            )

    # Checar se já tem matrícula ativa ou na fila nesta mesma turma
    matricula_existente = (
        db.query(Matricula)
        .filter(
            Matricula.aluno_id == aluno.id,
            Matricula.turma_id == turma.id,
            Matricula.estado.in_([
                EstadoMatricula.CONFIRMADA,
                EstadoMatricula.SOLICITADA,
                EstadoMatricula.LISTA_DE_ESPERA
            ])
        )
        .first()
    )
    if matricula_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Aluno já possui matrícula na turma {turma.id} com estado '{matricula_existente.estado.value}'."
        )

    # Checar se já tem matrícula confirmada em outra turma da mesma disciplina no mesmo semestre
    mesma_disciplina_no_semestre = (
        db.query(Matricula)
        .join(Turma)
        .filter(
            Matricula.aluno_id == aluno.id,
            Turma.semestre == turma.semestre,
            Turma.disciplina_id == turma.disciplina_id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        )
        .first()
    )
    if mesma_disciplina_no_semestre:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aluno já está matriculado na disciplina '{turma.disciplina.nome}' em outra turma neste mesmo semestre."
        )

    # REGRA 1: Limite de créditos por categoria no semestre
    # Somar créditos das turmas já confirmadas no mesmo semestre
    matriculas_confirmadas_semestre = (
        db.query(Matricula)
        .join(Turma)
        .join(Disciplina)
        .filter(
            Matricula.aluno_id == aluno.id,
            Turma.semestre == turma.semestre,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        )
        .all()
    )
    creditos_atuais = sum(m.turma.disciplina.numero_creditos for m in matriculas_confirmadas_semestre)
    creditos_tentativa = creditos_atuais + turma.disciplina.numero_creditos
    max_creditos = aluno.categoria.max_creditos

    if creditos_tentativa > max_creditos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Limite de créditos excedido para a categoria '{aluno.categoria.value}'. "
                f"Máximo: {max_creditos} créditos. Atuais: {creditos_atuais} créditos. "
                f"Tentativa com esta disciplina: {creditos_tentativa} créditos."
            )
        )

    # REGRA 6: Conflito de horário com turmas já confirmadas do aluno
    for m in matriculas_confirmadas_semestre:
        conflito = check_schedule_conflict(turma.horario, m.turma.horario)
        if conflito:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Conflito de horários com a turma {m.turma.id} ({m.turma.disciplina.nome}): "
                    f"'{conflito[0]}' choca com '{conflito[1]}'."
                )
            )

    # REGRA 2: Verificar se a turma está lotada
    processar_fila_espera(db, turma.id, data_ref=now)

    vagas_confirmadas = (
        db.query(Matricula)
        .filter(
            Matricula.turma_id == turma.id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        )
        .count()
    )

    vagas_reservadas = (
        db.query(Matricula)
        .filter(
            Matricula.turma_id == turma.id,
            Matricula.estado == EstadoMatricula.LISTA_DE_ESPERA,
            Matricula.limite_confirmacao_em.isnot(None),
            Matricula.limite_confirmacao_em > now,
        )
        .count()
    )

    total_ocupado = vagas_confirmadas + vagas_reservadas

    if total_ocupado >= turma.numero_vagas:
        # Turma lotada -> vai para lista de espera
        turma.estado = EstadoTurma.LOTADA
        nova_matricula = Matricula(
            aluno_id=aluno.id,
            turma_id=turma.id,
            data=now,
            estado=EstadoMatricula.LISTA_DE_ESPERA
        )
        db.add(nova_matricula)
        db.commit()
        db.refresh(nova_matricula)
        return nova_matricula

    # Vaga disponível
    if auto_confirm:
        nova_matricula = Matricula(
            aluno_id=aluno.id,
            turma_id=turma.id,
            data=now,
            estado=EstadoMatricula.CONFIRMADA
        )
        if total_ocupado + 1 >= turma.numero_vagas:
            turma.estado = EstadoTurma.LOTADA
    else:
        nova_matricula = Matricula(
            aluno_id=aluno.id,
            turma_id=turma.id,
            data=now,
            estado=EstadoMatricula.SOLICITADA
        )

    db.add(nova_matricula)
    db.commit()
    db.refresh(nova_matricula)
    return nova_matricula


def confirmar_matricula(
    db: Session,
    matricula_id: int,
    data_ref: Optional[datetime] = None
) -> Matricula:
    """
    Confirma uma matrícula solicitada ou que estava na lista de espera com vaga liberada dentro do prazo de 48h.
    """
    now = get_current_time(data_ref)
    matricula = db.query(Matricula).filter(Matricula.id == matricula_id).first()
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matrícula {matricula_id} não encontrada."
        )

    if matricula.estado == EstadoMatricula.CONFIRMADA:
        return matricula

    if matricula.estado in (EstadoMatricula.CANCELADA, EstadoMatricula.TRANCADA):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Matrícula não pode ser confirmada pois se encontra no estado '{matricula.estado.value}'."
        )

    aluno = matricula.aluno
    turma = matricula.turma

    # Verificar situação do aluno
    if aluno.situacao != SituacaoAluno.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aluno não está ativo ({aluno.situacao.value})."
        )

    # Se estava na lista de espera
    if matricula.estado == EstadoMatricula.LISTA_DE_ESPERA:
        if matricula.vaga_liberada_em is None or matricula.limite_confirmacao_em is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vaga ainda não liberada para esta matrícula na lista de espera."
            )

        limite = matricula.limite_confirmacao_em
        if limite.tzinfo is None:
            limite = limite.replace(tzinfo=timezone.utc)

        # Regra 2: esgotado o prazo de 48h, a matrícula é cancelada e a vez passa ao próximo
        if now > limite:
            matricula.estado = EstadoMatricula.CANCELADA
            matricula.vaga_liberada_em = None
            matricula.limite_confirmacao_em = None
            db.commit()
            processar_fila_espera(db, turma.id, data_ref=now)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prazo de 48 horas expirado para confirmação da vaga. Matrícula cancelada e vaga passada ao próximo da fila."
            )

    # Checar créditos e conflito de horário no momento da confirmação
    matriculas_confirmadas_semestre = (
        db.query(Matricula)
        .join(Turma)
        .filter(
            Matricula.aluno_id == aluno.id,
            Turma.semestre == turma.semestre,
            Matricula.estado == EstadoMatricula.CONFIRMADA,
            Matricula.id != matricula.id
        )
        .all()
    )

    creditos_atuais = sum(m.turma.disciplina.numero_creditos for m in matriculas_confirmadas_semestre)
    if creditos_atuais + turma.disciplina.numero_creditos > aluno.categoria.max_creditos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível confirmar: limite de créditos da categoria foi atingido."
        )

    for m in matriculas_confirmadas_semestre:
        conflito = check_schedule_conflict(turma.horario, m.turma.horario)
        if conflito:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Não é possível confirmar: conflito de horário com a turma {m.turma.id}."
            )

    # Confirmar
    matricula.estado = EstadoMatricula.CONFIRMADA
    matricula.vaga_liberada_em = None
    matricula.limite_confirmacao_em = None

    # Atualizar estado da turma
    total_confirmadas = (
        db.query(Matricula)
        .filter(
            Matricula.turma_id == turma.id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        )
        .count()
    ) + 1  # contando esta

    if total_confirmadas >= turma.numero_vagas:
        turma.estado = EstadoTurma.LOTADA

    db.commit()
    db.refresh(matricula)
    return matricula


def cancelar_matricula(
    db: Session,
    matricula_id: int,
    data_ref: Optional[datetime] = None
) -> Tuple[Matricula, str]:
    """
    Cancela a matrícula aplicando a Regra 4:
    "O trancamento de uma disciplina so e permitido dentro do prazo de cancelamento da categoria e respeitando o limite de trancamentos.
    Fora do prazo, o cancelamento registra reprovacao por falta no historico."
    """
    now = get_current_time(data_ref)
    matricula = db.query(Matricula).filter(Matricula.id == matricula_id).first()
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matrícula {matricula_id} não encontrada."
        )

    if matricula.estado in (EstadoMatricula.CANCELADA, EstadoMatricula.TRANCADA):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Matrícula já se encontra no estado '{matricula.estado.value}'."
        )

    aluno = matricula.aluno
    turma = matricula.turma
    era_confirmada = (matricula.estado == EstadoMatricula.CONFIRMADA)
    mensagem = "Matrícula cancelada com sucesso."

    if era_confirmada:
        mat_data = matricula.data
        if mat_data.tzinfo is None:
            mat_data = mat_data.replace(tzinfo=timezone.utc)
        dias_decorridos = (now - mat_data).days
        prazo_limite = aluno.categoria.prazo_cancelamento_dias

        # REGRA 4: Fora do prazo, cancelamento registra reprovação por falta no histórico
        if dias_decorridos > prazo_limite:
            hist = Historico(
                aluno_id=aluno.id,
                disciplina_id=turma.disciplina_id,
                semestre=turma.semestre,
                nota=0.0,
                situacao=SituacaoHistorico.REPROVADO_POR_FALTA
            )
            db.add(hist)
            mensagem = (
                f"Matrícula cancelada fora do prazo ({dias_decorridos} dias decorridos > {prazo_limite} dias permitidos). "
                f"Registrada reprovação por falta no histórico acadêmico."
            )

    matricula.estado = EstadoMatricula.CANCELADA
    matricula.vaga_liberada_em = None
    matricula.limite_confirmacao_em = None
    db.commit()

    # Se liberou vaga, chama a fila de espera
    if era_confirmada or turma.estado == EstadoTurma.LOTADA:
        processar_fila_espera(db, turma.id, data_ref=now)

    db.refresh(matricula)
    return matricula, mensagem


def trancar_matricula(
    db: Session,
    matricula_id: int,
    data_ref: Optional[datetime] = None
) -> Tuple[Matricula, str]:
    """
    Tranca a matrícula aplicando as Regras 4 e 7:
    - Regra 4: Permitido apenas dentro do prazo de cancelamento da categoria e respeitando o limite de trancamentos por disciplina.
    - Regra 7: Aluno que acumular 3 trancamentos no semestre passa a situação 'trancado' e todas as suas matrículas confirmadas são canceladas.
    """
    now = get_current_time(data_ref)
    matricula = db.query(Matricula).filter(Matricula.id == matricula_id).first()
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matrícula {matricula_id} não encontrada."
        )

    if matricula.estado != EstadoMatricula.CONFIRMADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Apenas matrículas confirmadas podem ser trancadas. Estado atual: '{matricula.estado.value}'."
        )

    aluno = matricula.aluno
    turma = matricula.turma

    # Categoria Especial: nenhum trancamento permitido
    if aluno.categoria == CategoriaAluno.ESPECIAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alunos da categoria 'especial' não possuem permissão para trancar disciplinas."
        )

    # Prazo de trancamento/cancelamento da categoria
    mat_data = matricula.data
    if mat_data.tzinfo is None:
        mat_data = mat_data.replace(tzinfo=timezone.utc)
    dias_decorridos = (now - mat_data).days
    prazo_limite = aluno.categoria.prazo_cancelamento_dias

    if dias_decorridos > prazo_limite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Prazo para trancamento expirado: decorridos {dias_decorridos} dias "
                f"(máximo permitido para {aluno.categoria.value}: {prazo_limite} dias)."
            )
        )

    # Limite de trancamentos por disciplina
    trancamentos_anteriores = (
        db.query(Historico)
        .filter(
            Historico.aluno_id == aluno.id,
            Historico.disciplina_id == turma.disciplina_id,
            Historico.situacao == SituacaoHistorico.TRANCADO
        )
        .count()
    )
    max_trancamentos = aluno.categoria.max_trancamentos
    if trancamentos_anteriores >= max_trancamentos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Limite de trancamentos atingido para esta disciplina. "
                f"Já foram realizados {trancamentos_anteriores} trancamentos (máximo: {max_trancamentos})."
            )
        )

    # Realizar o trancamento
    matricula.estado = EstadoMatricula.TRANCADA
    matricula.vaga_liberada_em = None
    matricula.limite_confirmacao_em = None

    # Registrar no histórico como trancado
    hist = Historico(
        aluno_id=aluno.id,
        disciplina_id=turma.disciplina_id,
        semestre=turma.semestre,
        nota=None,
        situacao=SituacaoHistorico.TRANCADO
    )
    db.add(hist)
    db.flush()

    mensagem = "Matrícula trancada com sucesso."
    turmas_para_reprocessar = [turma.id]

    # REGRA 7: Acumular 3 trancamentos no semestre tranca o aluno e cancela suas matrículas confirmadas
    trancamentos_no_semestre = (
        db.query(Historico)
        .filter(
            Historico.aluno_id == aluno.id,
            Historico.semestre == turma.semestre,
            Historico.situacao == SituacaoHistorico.TRANCADO
        )
        .count()
    )

    if trancamentos_no_semestre >= settings.MAX_TRANCAMENTOS_SEMESTRE_ALUNO:
        aluno.situacao = SituacaoAluno.TRANCADO
        # Cancelar todas as demais matrículas confirmadas do aluno no semestre
        outras_matriculas = (
            db.query(Matricula)
            .join(Turma)
            .filter(
                Matricula.aluno_id == aluno.id,
                Turma.semestre == turma.semestre,
                Matricula.estado == EstadoMatricula.CONFIRMADA
            )
            .all()
        )
        for m in outras_matriculas:
            m.estado = EstadoMatricula.CANCELADA
            if m.turma_id not in turmas_para_reprocessar:
                turmas_para_reprocessar.append(m.turma_id)

        mensagem += (
            f" Aluno atingiu {trancamentos_no_semestre} trancamentos no semestre {turma.semestre}. "
            f"Situação do aluno alterada para 'trancado' e todas as suas demais matrículas confirmadas foram canceladas."
        )

    db.commit()

    # Processar fila de espera para as turmas onde foram abertas vagas
    for tid in turmas_para_reprocessar:
        processar_fila_espera(db, tid, data_ref=now)

    db.refresh(matricula)
    return matricula, mensagem
