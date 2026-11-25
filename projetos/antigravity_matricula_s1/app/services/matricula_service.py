from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.aluno import Aluno
from app.models.disciplina import Disciplina
from app.models.prerequisito import PreRequisito
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
from app.config import (
    REGRAS_POR_CATEGORIA,
    MAX_REPROVACOES_IMPEDIMENTO,
    HORAS_CONFIRMACAO_VAGA_LIBERADA,
    MINIMO_MATRICULAS_TURMA,
    MAX_TRANCAMENTOS_SEMESTRE_TRANCAR_ALUNO,
)
from app.services.horario_service import verificar_conflito_horarios


def normalizar_datetime_utc(dt: Optional[datetime]) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def atualizar_estado_turma(db: Session, turma_id: int) -> Turma:
    """Atualiza o estado da turma para lotada ou aberta com base no número de vagas."""
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma or turma.estado in (EstadoTurma.CANCELADA, EstadoTurma.ENCERRADA):
        return turma

    # Contar vagas ocupadas por matrículas confirmadas e solicitadas com vaga reservada
    ocupadas = db.query(Matricula).filter(
        Matricula.turma_id == turma_id,
        Matricula.estado.in_([EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA])
    ).count()

    if ocupadas >= turma.numero_vagas:
        turma.estado = EstadoTurma.LOTADA
    else:
        turma.estado = EstadoTurma.ABERTA

    db.commit()
    db.refresh(turma)
    return turma


def processar_expiracoes_48h(db: Session, turma_id: Optional[int] = None) -> List[int]:
    """
    Verifica se alguma matrícula no estado SOLICITADA com prazo de 48h expirou.
    Se expirou, cancela a matrícula e passa a vaga para o próximo da lista de espera.
    """
    agora = datetime.now(timezone.utc)
    query = db.query(Matricula).filter(
        Matricula.estado == EstadoMatricula.SOLICITADA,
        Matricula.data_limite_confirmacao.isnot(None),
        Matricula.data_limite_confirmacao < agora,
    )
    if turma_id:
        query = query.filter(Matricula.turma_id == turma_id)

    expiradas = query.all()
    turmas_afetadas = set()
    ids_cancelados = []

    for m in expiradas:
        m.estado = EstadoMatricula.CANCELADA
        m.data_limite_confirmacao = None
        ids_cancelados.append(m.id)
        turmas_afetadas.add(m.turma_id)

    if expiradas:
        db.commit()
        for t_id in turmas_afetadas:
            processar_proximo_fila_espera(db, t_id)
            atualizar_estado_turma(db, t_id)

    return ids_cancelados


def obter_fila_espera_ordenada(db: Session, turma_id: int) -> List[Matricula]:
    """
    Retorna a fila de espera de uma turma ordenada por:
    1. Prioridade da categoria (Pós: 1, Graduação: 2, Especial: 3)
    2. Data da solicitação ASC (mais antiga primeiro)
    """
    matriculas_espera = db.query(Matricula).join(Aluno).filter(
        Matricula.turma_id == turma_id,
        Matricula.estado == EstadoMatricula.LISTA_DE_ESPERA
    ).all()

    def chave_ordenacao(m: Matricula):
        cat_str = m.aluno.categoria.value if hasattr(m.aluno.categoria, "value") else str(m.aluno.categoria)
        regra = REGRAS_POR_CATEGORIA.get(cat_str)
        prio = regra.prioridade_espera if regra else 99
        dt = normalizar_datetime_utc(m.data)
        return (prio, dt, m.id)

    return sorted(matriculas_espera, key=chave_ordenacao)


def processar_proximo_fila_espera(db: Session, turma_id: int) -> Optional[Matricula]:
    """
    Quando uma vaga é liberada, o primeiro da fila tem 48 horas para confirmar.
    Sua matrícula passa ao estado 'solicitada' e recebe data_limite_confirmacao = now + 48h.
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma or turma.estado in (EstadoTurma.CANCELADA, EstadoTurma.ENCERRADA):
        return None

    # Contar vagas ocupadas
    vagas_ocupadas = db.query(Matricula).filter(
        Matricula.turma_id == turma_id,
        Matricula.estado.in_([EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA])
    ).count()

    vagas_livres = turma.numero_vagas - vagas_ocupadas
    if vagas_livres <= 0:
        return None

    fila = obter_fila_espera_ordenada(db, turma_id)
    if not fila:
        return None

    primeiro = fila[0]
    primeiro.estado = EstadoMatricula.SOLICITADA
    primeiro.data_limite_confirmacao = datetime.now(timezone.utc) + timedelta(hours=HORAS_CONFIRMACAO_VAGA_LIBERADA)
    db.commit()
    db.refresh(primeiro)
    atualizar_estado_turma(db, turma_id)
    return primeiro


def solicitar_matricula(
    db: Session,
    aluno_id: int,
    turma_id: int,
    data: Optional[datetime] = None,
    auto_confirm: Optional[bool] = None,
) -> Matricula:
    """
    Executa todas as validações e regras de negócio para a solicitação de matrícula:
    - Regra 1: Aluno ativo, pré-requisitos cumpridos, limite de créditos da categoria.
    - Regra 2: Turma lotada -> lista de espera ordenada por prioridade da categoria e data.
    - Regra 3: Aluno reprovado 3x na disciplina é impedido.
    - Regra 6: Conflito de horário com turma já confirmada é negado.
    """
    # Processa expirações de 48h pendentes
    processar_expiracoes_48h(db, turma_id)

    # 1. Aluno existe e ativo
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado")

    situacao_val = aluno.situacao.value if hasattr(aluno.situacao, "value") else str(aluno.situacao)
    if situacao_val != SituacaoAluno.ATIVO.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Matrícula negada: aluno não está ativo. Situação atual: {situacao_val}"
        )

    # 2. Turma existe e está aberta/lotada
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada")

    estado_turma_val = turma.estado.value if hasattr(turma.estado, "value") else str(turma.estado)
    if estado_turma_val in (EstadoTurma.CANCELADA.value, EstadoTurma.ENCERRADA.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Matrícula negada: turma está {estado_turma_val}"
        )

    # 3. Regra 3: Aluno reprovado 3 vezes na mesma disciplina fica impedido
    reprovacoes = db.query(Historico).filter(
        Historico.aluno_id == aluno.id,
        Historico.disciplina_id == turma.disciplina_id,
        Historico.situacao.in_([
            SituacaoHistorico.REPROVADO,
            SituacaoHistorico.REPROVADO_POR_FALTA,
        ])
    ).count()

    if reprovacoes >= MAX_REPROVACOES_IMPEDIMENTO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Matrícula negada: aluno reprovado {reprovacoes} vezes nesta disciplina (máximo permitido: {MAX_REPROVACOES_IMPEDIMENTO - 1})"
        )

    # 4. Regra 1: Pré-requisitos cumpridos
    prereqs = db.query(PreRequisito).filter(PreRequisito.disciplina_id == turma.disciplina_id).all()
    for pr in prereqs:
        aprovado = db.query(Historico).filter(
            Historico.aluno_id == aluno.id,
            Historico.disciplina_id == pr.prerequisito_id,
            Historico.situacao == SituacaoHistorico.APROVADO
        ).first()
        if not aprovado:
            disc_pr = db.query(Disciplina).filter(Disciplina.id == pr.prerequisito_id).first()
            codigo_pr = disc_pr.codigo if disc_pr else str(pr.prerequisito_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Matrícula negada: pré-requisito não cumprido ({codigo_pr})"
            )

    # 5. Já matriculado nesta turma?
    matricula_existente = db.query(Matricula).filter(
        Matricula.aluno_id == aluno.id,
        Matricula.turma_id == turma.id,
        Matricula.estado.in_([
            EstadoMatricula.SOLICITADA,
            EstadoMatricula.CONFIRMADA,
            EstadoMatricula.LISTA_DE_ESPERA,
        ])
    ).first()
    if matricula_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aluno já possui matrícula com estado '{matricula_existente.estado.value}' nesta turma"
        )

    # Já matriculado em outra turma da mesma disciplina no mesmo semestre?
    outra_turma_mesma_disciplina = db.query(Matricula).join(Turma).filter(
        Matricula.aluno_id == aluno.id,
        Turma.disciplina_id == turma.disciplina_id,
        Turma.semestre == turma.semestre,
        Matricula.estado.in_([EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA])
    ).first()
    if outra_turma_mesma_disciplina:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aluno já possui matrícula ativa nesta disciplina no mesmo semestre"
        )

    # 6. Regra 6: Conflito de horário com turma já confirmada do aluno
    matriculas_confirmadas_semestre = db.query(Matricula).join(Turma).filter(
        Matricula.aluno_id == aluno.id,
        Turma.semestre == turma.semestre,
        Matricula.estado == EstadoMatricula.CONFIRMADA
    ).all()

    for mc in matriculas_confirmadas_semestre:
        if verificar_conflito_horarios(turma.horario, mc.turma.horario):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Matrícula negada: conflito de horário ({turma.horario}) com turma já confirmada ({mc.turma.horario} - {mc.turma.disciplina.codigo})"
            )

    # 7. Regra 1: Limite de créditos por categoria no semestre
    cat_str = aluno.categoria.value if hasattr(aluno.categoria, "value") else str(aluno.categoria)
    regra_cat = REGRAS_POR_CATEGORIA.get(cat_str)
    if not regra_cat:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Categoria de aluno inválida")

    creditos_atuais = sum(
        mc.turma.disciplina.numero_creditos for mc in matriculas_confirmadas_semestre
    )
    creditos_novos = turma.disciplina.numero_creditos

    if creditos_atuais + creditos_novos > regra_cat.max_creditos_semestre:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Matrícula negada: limite de créditos da categoria {cat_str} excedido ({creditos_atuais + creditos_novos} > {regra_cat.max_creditos_semestre})"
        )

    # 8. Regra 2: Verificação de vagas e lotação
    vagas_ocupadas = db.query(Matricula).filter(
        Matricula.turma_id == turma.id,
        Matricula.estado.in_([EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA])
    ).count()

    dt_solicitacao = normalizar_datetime_utc(data)

    if vagas_ocupadas >= turma.numero_vagas:
        # Turma lotada -> entra em lista de espera
        turma.estado = EstadoTurma.LOTADA
        nova_matricula = Matricula(
            aluno_id=aluno.id,
            turma_id=turma.id,
            data=dt_solicitacao,
            estado=EstadoMatricula.LISTA_DE_ESPERA,
            data_limite_confirmacao=None,
        )
        db.add(nova_matricula)
        db.commit()
        db.refresh(nova_matricula)
        return nova_matricula

    # Há vaga na turma!
    # Padrão: auto_confirm=True (confirma diretamente quando há vaga, respeitando a regra)
    deve_confirmar = True if auto_confirm is None or auto_confirm is True else False
    estado_final = EstadoMatricula.CONFIRMADA if deve_confirmar else EstadoMatricula.SOLICITADA

    nova_matricula = Matricula(
        aluno_id=aluno.id,
        turma_id=turma.id,
        data=dt_solicitacao,
        estado=estado_final,
        data_limite_confirmacao=None,
    )
    db.add(nova_matricula)
    db.commit()
    db.refresh(nova_matricula)

    # Atualiza estado da turma se lotou
    atualizar_estado_turma(db, turma.id)
    return nova_matricula


def confirmar_matricula(db: Session, matricula_id: int) -> Matricula:
    """
    Confirma uma matrícula.
    Utilizada quando:
    - O aluno foi promovido da lista de espera e está dentro do prazo de 48h.
    - O aluno possui uma matrícula no estado 'solicitada'.
    - É idempotente caso já esteja confirmada.
    """
    matricula = db.query(Matricula).filter(Matricula.id == matricula_id).first()
    if not matricula:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matrícula não encontrada")

    # Idempotência
    if matricula.estado == EstadoMatricula.CONFIRMADA:
        return matricula

    if matricula.estado in (EstadoMatricula.CANCELADA, EstadoMatricula.TRANCADA):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não é possível confirmar uma matrícula {matricula.estado.value}"
        )

    # Se estiver no estado SOLICITADA (como primeiro da lista ou solicitação pendente)
    if matricula.estado == EstadoMatricula.SOLICITADA:
        # Verifica se o prazo de 48h expirou
        if matricula.data_limite_confirmacao:
            limite_utc = normalizar_datetime_utc(matricula.data_limite_confirmacao)
            agora_utc = datetime.now(timezone.utc)
            if agora_utc > limite_utc:
                matricula.estado = EstadoMatricula.CANCELADA
                matricula.data_limite_confirmacao = None
                db.commit()
                processar_proximo_fila_espera(db, matricula.turma_id)
                atualizar_estado_turma(db, matricula.turma_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Prazo de 48 horas para confirmação expirado. Matrícula cancelada."
                )

        # Regra 6: Verificar se não conflita com outra turma confirmada
        outras_confirmadas = db.query(Matricula).join(Turma).filter(
            Matricula.aluno_id == matricula.aluno_id,
            Turma.semestre == matricula.turma.semestre,
            Matricula.estado == EstadoMatricula.CONFIRMADA,
            Matricula.id != matricula.id
        ).all()

        for mc in outras_confirmadas:
            if verificar_conflito_horarios(matricula.turma.horario, mc.turma.horario):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Conflito de horário com turma já confirmada ({mc.turma.horario} - {mc.turma.disciplina.codigo})"
                )

        # Regra 1: Verificar se não excede limite de créditos
        cat_str = matricula.aluno.categoria.value if hasattr(matricula.aluno.categoria, "value") else str(matricula.aluno.categoria)
        regra_cat = REGRAS_POR_CATEGORIA.get(cat_str)
        creditos_atuais = sum(mc.turma.disciplina.numero_creditos for mc in outras_confirmadas)
        if creditos_atuais + matricula.turma.disciplina.numero_creditos > regra_cat.max_creditos_semestre:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Limite de créditos excedido para a categoria {cat_str}"
            )

        matricula.estado = EstadoMatricula.CONFIRMADA
        matricula.data_limite_confirmacao = None
        db.commit()
        db.refresh(matricula)
        atualizar_estado_turma(db, matricula.turma_id)
        return matricula

    # Se estiver em LISTA_DE_ESPERA
    if matricula.estado == EstadoMatricula.LISTA_DE_ESPERA:
        # Verifica se há vaga e se é o primeiro da fila
        fila = obter_fila_espera_ordenada(db, matricula.turma_id)
        if fila and fila[0].id == matricula.id:
            # Primeiro da fila: passa para confirmada se houver vaga
            vagas_ocupadas = db.query(Matricula).filter(
                Matricula.turma_id == matricula.turma_id,
                Matricula.estado == EstadoMatricula.CONFIRMADA
            ).count()
            if vagas_ocupadas < matricula.turma.numero_vagas:
                matricula.estado = EstadoMatricula.CONFIRMADA
                matricula.data_limite_confirmacao = None
                db.commit()
                db.refresh(matricula)
                atualizar_estado_turma(db, matricula.turma_id)
                return matricula

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aluno está na lista de espera. A vaga ainda não foi liberada para confirmação."
        )

    return matricula


def cancelar_matricula(
    db: Session,
    matricula_id: int,
    data_cancelamento: Optional[datetime] = None
) -> Matricula:
    """
    Cancela uma matrícula.
    - Se estiver em lista de espera ou solicitada, simplesmente cancela.
    - Se confirmada, verifica prazo da categoria:
      - Dentro do prazo: cancela sem penalidade.
      - Fora do prazo: cancela e registra reprovação por falta no histórico (Regra 4).
    - Libera vaga e notifica o próximo da fila de espera com 48h (Regra 2).
    """
    matricula = db.query(Matricula).filter(Matricula.id == matricula_id).first()
    if not matricula:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matrícula não encontrada")

    if matricula.estado == EstadoMatricula.CANCELADA:
        return matricula

    turma_id = matricula.turma_id
    estado_anterior = matricula.estado

    if estado_anterior == EstadoMatricula.CONFIRMADA:
        aluno = matricula.aluno
        cat_str = aluno.categoria.value if hasattr(aluno.categoria, "value") else str(aluno.categoria)
        regra_cat = REGRAS_POR_CATEGORIA.get(cat_str)

        dt_canc = normalizar_datetime_utc(data_cancelamento)
        dt_mat = normalizar_datetime_utc(matricula.data)
        dias_passados = (dt_canc.date() - dt_mat.date()).days

        if dias_passados > regra_cat.prazo_cancelamento_dias:
            # Regra 4: Fora do prazo, o cancelamento registra reprovação por falta no histórico
            hist = Historico(
                aluno_id=aluno.id,
                disciplina_id=matricula.turma.disciplina_id,
                semestre=matricula.turma.semestre,
                nota=0.0,
                situacao=SituacaoHistorico.REPROVADO_POR_FALTA,
            )
            db.add(hist)

    matricula.estado = EstadoMatricula.CANCELADA
    matricula.data_limite_confirmacao = None
    db.commit()
    db.refresh(matricula)

    # Se liberou vaga, passa ao próximo da fila de espera
    if estado_anterior in (EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA):
        processar_proximo_fila_espera(db, turma_id)
        atualizar_estado_turma(db, turma_id)

    return matricula


def trancar_matricula(
    db: Session,
    matricula_id: int,
    data_trancamento: Optional[datetime] = None
) -> Matricula:
    """
    Executa o trancamento de uma matrícula:
    - Regra 4: O trancamento de uma disciplina só é permitido dentro do prazo de cancelamento
      da categoria e respeitando o limite de trancamentos. Fora do prazo, o cancelamento
      registra reprovação por falta no histórico.
    - Regra 7: Aluno que acumular três trancamentos no semestre passa à situação 'trancado',
      e todas as suas matrículas confirmadas são canceladas.
    """
    matricula = db.query(Matricula).filter(Matricula.id == matricula_id).first()
    if not matricula:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matrícula não encontrada")

    if matricula.estado == EstadoMatricula.TRANCADA:
        return matricula

    if matricula.estado != EstadoMatricula.CONFIRMADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Apenas matrículas confirmadas podem ser trancadas. Estado atual: {matricula.estado.value}"
        )

    aluno = matricula.aluno
    cat_str = aluno.categoria.value if hasattr(aluno.categoria, "value") else str(aluno.categoria)
    regra_cat = REGRAS_POR_CATEGORIA.get(cat_str)

    # 1. Verifica limite de trancamentos por disciplina da categoria
    # Especial: 0 trancamentos
    # Pos: 1 trancamento
    # Graduacao: 2 trancamentos
    trancamentos_anteriores = db.query(Historico).filter(
        Historico.aluno_id == aluno.id,
        Historico.disciplina_id == matricula.turma.disciplina_id,
        Historico.situacao == SituacaoHistorico.TRANCADO
    ).count()

    if trancamentos_anteriores >= regra_cat.max_trancamentos_disciplina:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trancamento negado: limite de trancamentos para esta disciplina atingido ({trancamentos_anteriores} de {regra_cat.max_trancamentos_disciplina} permitidos para {cat_str})"
        )

    # 2. Verifica prazo de cancelamento da categoria
    dt_tranc = normalizar_datetime_utc(data_trancamento)
    dt_mat = normalizar_datetime_utc(matricula.data)
    dias_passados = (dt_tranc.date() - dt_mat.date()).days

    turma_id = matricula.turma_id
    semestre_turma = matricula.turma.semestre
    disciplina_id = matricula.turma.disciplina_id

    if dias_passados > regra_cat.prazo_cancelamento_dias:
        # Fora do prazo: registra reprovação por falta no histórico e cancela a matrícula
        matricula.estado = EstadoMatricula.CANCELADA
        hist = Historico(
            aluno_id=aluno.id,
            disciplina_id=disciplina_id,
            semestre=semestre_turma,
            nota=0.0,
            situacao=SituacaoHistorico.REPROVADO_POR_FALTA,
        )
        db.add(hist)
        db.commit()
        db.refresh(matricula)
        processar_proximo_fila_espera(db, turma_id)
        atualizar_estado_turma(db, turma_id)
        return matricula

    # Dentro do prazo e dentro do limite: trancamento com sucesso
    matricula.estado = EstadoMatricula.TRANCADA
    hist = Historico(
        aluno_id=aluno.id,
        disciplina_id=disciplina_id,
        semestre=semestre_turma,
        nota=None,
        situacao=SituacaoHistorico.TRANCADO,
    )
    db.add(hist)
    db.commit()
    db.refresh(matricula)

    # 3. Regra 7: Aluno que acumular três trancamentos no semestre passa à situação 'trancado',
    # e todas as suas matrículas confirmadas são canceladas.
    trancamentos_semestre = db.query(Historico).filter(
        Historico.aluno_id == aluno.id,
        Historico.semestre == semestre_turma,
        Historico.situacao == SituacaoHistorico.TRANCADO
    ).count()

    if trancamentos_semestre >= MAX_TRANCAMENTOS_SEMESTRE_TRANCAR_ALUNO:
        aluno.situacao = SituacaoAluno.TRANCADO
        matriculas_confirmadas = db.query(Matricula).join(Turma).filter(
            Matricula.aluno_id == aluno.id,
            Turma.semestre == semestre_turma,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        ).all()

        turmas_liberadas = []
        for mc in matriculas_confirmadas:
            mc.estado = EstadoMatricula.CANCELADA
            turmas_liberadas.append(mc.turma_id)

        db.commit()

        for tid in turmas_liberadas:
            processar_proximo_fila_espera(db, tid)
            atualizar_estado_turma(db, tid)

    # Libera a vaga desta turma
    processar_proximo_fila_espera(db, turma_id)
    atualizar_estado_turma(db, turma_id)
    return matricula


def encerrar_periodo_matricula_turma(db: Session, turma_id: int) -> Turma:
    """
    Regra 5: Turma com menos de 5 matrículas confirmadas ao fim do período de matrícula
    é cancelada, e todas as suas matrículas passam ao estado cancelada.
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada")

    if turma.estado == EstadoTurma.CANCELADA:
        return turma

    matriculas_confirmadas = db.query(Matricula).filter(
        Matricula.turma_id == turma_id,
        Matricula.estado == EstadoMatricula.CONFIRMADA
    ).count()

    if matriculas_confirmadas < MINIMO_MATRICULAS_TURMA:
        turma.estado = EstadoTurma.CANCELADA
        # Todas as suas matrículas passam ao estado cancelada
        todas_matriculas = db.query(Matricula).filter(Matricula.turma_id == turma_id).all()
        for m in todas_matriculas:
            m.estado = EstadoMatricula.CANCELADA
            m.data_limite_confirmacao = None
        db.commit()
    else:
        # Turma mantida
        if turma.estado == EstadoTurma.ABERTA:
            turma.estado = EstadoTurma.ENCERRADA
        db.commit()

    db.refresh(turma)
    return turma
