from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.matricula import Matricula
from app.models.aluno import Aluno
from app.models.turma import Turma
from app.models.disciplina import PreRequisito
from app.models.historico import Historico
from app.config import (
    CategoriaAluno,
    SituacaoAluno,
    EstadoTurma,
    EstadoMatricula,
    SituacaoHistorico,
    REGRAS_CATEGORIAS,
    MAX_REPROVACOES_DISCIPLINA,
    HORAS_EXPIRACAO_VAGA_FILA,
    MAX_TRANCAMENTOS_SEMESTRE_ALUNO,
)
from app.services.schedule_parser import has_schedule_conflict
from app.services.historico_service import (
    count_reprovacoes_disciplina,
    is_aprovado_na_disciplina,
    count_trancamentos_disciplina,
    count_trancamentos_semestre,
)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_current_time(simulated_now: Optional[datetime] = None) -> datetime:
    if simulated_now is not None:
        return ensure_utc(simulated_now)
    return datetime.now(timezone.utc)


def get_matricula_by_id(db: Session, matricula_id: int) -> Matricula:
    matricula = db.query(Matricula).filter(Matricula.id == matricula_id).first()
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matrícula com ID {matricula_id} não encontrada."
        )
    return matricula


def list_matriculas_por_aluno(db: Session, aluno_id: int) -> List[Matricula]:
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aluno com ID {aluno_id} não encontrado."
        )
    return db.query(Matricula).filter(Matricula.aluno_id == aluno_id).all()


def count_vagas_ocupadas_turma(db: Session, turma_id: int) -> int:
    """
    Conta matrículas ocupando vagas (confirmadas ou solicitadas com oferta ativa de 48h).
    """
    return db.query(Matricula).filter(
        Matricula.turma_id == turma_id,
        Matricula.estado.in_([EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA])
    ).count()


def calcular_creditos_aluno_semestre(db: Session, aluno_id: int, semestre: str) -> int:
    """
    Calcula os créditos acumulados pelo aluno em turmas com matrícula confirmada ou solicitada no semestre.
    """
    matriculas = db.query(Matricula).join(Turma).filter(
        Matricula.aluno_id == aluno_id,
        Turma.semestre == semestre,
        Matricula.estado.in_([EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA])
    ).all()

    total = 0
    for m in matriculas:
        total += m.turma.disciplina.numero_creditos
    return total


def verificar_conflito_horario(db: Session, aluno_id: int, nova_turma: Turma) -> None:
    """
    Regra 6: Matrícula em turma cujo horário conflita com outra turma já confirmada do aluno é negada.
    """
    matriculas_confirmadas = db.query(Matricula).join(Turma).filter(
        Matricula.aluno_id == aluno_id,
        Turma.semestre == nova_turma.semestre,
        Matricula.estado == EstadoMatricula.CONFIRMADA,
        Matricula.turma_id != nova_turma.id
    ).all()

    for m in matriculas_confirmadas:
        outra_turma = m.turma
        if has_schedule_conflict(nova_turma.horario, outra_turma.horario):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Conflito de horário detectado: Turma {nova_turma.id} ({nova_turma.horario}) "
                    f"conflita com a turma {outra_turma.id} - {outra_turma.disciplina.nome} ({outra_turma.horario}) "
                    f"já confirmada para o aluno."
                )
            )


def processar_expiracoes_e_fila(db: Session, turma_id: int, simulated_now: Optional[datetime] = None) -> None:
    """
    Regra 2: Quando uma vaga é liberada, o primeiro da fila tem 48 horas para confirmar;
    esgotado o prazo, a matrícula é cancelada e a vez passa ao próximo.
    """
    now = get_current_time(simulated_now)
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        return

    # 1. Verificar se há ofertas em SOLICITADA expiradas
    ofertas_pendentes = db.query(Matricula).filter(
        Matricula.turma_id == turma_id,
        Matricula.estado == EstadoMatricula.SOLICITADA,
        Matricula.data_oferta_vaga.isnot(None)
    ).all()

    for oferta in ofertas_pendentes:
        data_oferta = ensure_utc(oferta.data_oferta_vaga)
        if (now - data_oferta).total_seconds() > HORAS_EXPIRACAO_VAGA_FILA * 3600:
            # Expirou! Cancela e libera para o próximo
            oferta.estado = EstadoMatricula.CANCELADA
            db.commit()

    # 2. Calcular vagas disponíveis
    ocupadas = count_vagas_ocupadas_turma(db, turma_id)
    vagas_disponiveis = turma.numero_vagas - ocupadas

    # 3. Se houver vagas disponíveis, chamar os próximos da fila
    while vagas_disponiveis > 0:
        candidatos = db.query(Matricula).filter(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.LISTA_DE_ESPERA
        ).all()

        if not candidatos:
            break

        # Ordenar por prioridade da categoria (1=alta, 2=media, 3=baixa) e depois por data
        candidatos.sort(
            key=lambda m: (
                REGRAS_CATEGORIAS[m.aluno.categoria].prioridade_lista_espera,
                ensure_utc(m.data)
            )
        )

        proximo = candidatos[0]
        proximo.estado = EstadoMatricula.SOLICITADA
        proximo.data_oferta_vaga = now
        db.commit()

        vagas_disponiveis -= 1

    # Atualizar estado da turma
    ocupadas_final = count_vagas_ocupadas_turma(db, turma_id)
    if turma.estado not in [EstadoTurma.CANCELADA, EstadoTurma.ENCERRADA]:
        if ocupadas_final >= turma.numero_vagas:
            turma.estado = EstadoTurma.LOTADA
        else:
            turma.estado = EstadoTurma.ABERTA
        db.commit()


def obter_fila_espera(db: Session, turma_id: int, simulated_now: Optional[datetime] = None) -> List[dict]:
    """
    Retorna a fila de espera ordenada e atualizada de uma turma.
    """
    processar_expiracoes_e_fila(db, turma_id, simulated_now)
    now = get_current_time(simulated_now)

    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turma com ID {turma_id} não encontrada."
        )

    # Buscar quem está com oferta pendente (SOLICITADA com data_oferta_vaga) e LISTA_DE_ESPERA
    em_espera = db.query(Matricula).filter(
        Matricula.turma_id == turma_id,
        Matricula.estado.in_([EstadoMatricula.LISTA_DE_ESPERA, EstadoMatricula.SOLICITADA])
    ).all()

    # Separar os que estão com oferta ativa (posição de topo com 48h para confirmar) e os em espera
    com_oferta = [m for m in em_espera if m.estado == EstadoMatricula.SOLICITADA and m.data_oferta_vaga]
    na_fila = [m for m in em_espera if m.estado == EstadoMatricula.LISTA_DE_ESPERA]

    # Ordenar quem tem oferta por data da oferta
    com_oferta.sort(key=lambda m: ensure_utc(m.data_oferta_vaga))

    # Ordenar fila de espera pela prioridade da categoria e data da solicitação
    na_fila.sort(
        key=lambda m: (
            REGRAS_CATEGORIAS[m.aluno.categoria].prioridade_lista_espera,
            ensure_utc(m.data)
        )
    )

    fila_completa = com_oferta + na_fila
    resultado = []
    for idx, m in enumerate(fila_completa, start=1):
        horas_restantes = None
        prazo_limite = None
        if m.data_oferta_vaga:
            data_o = ensure_utc(m.data_oferta_vaga)
            prazo_limite = data_o + timedelta(hours=HORAS_EXPIRACAO_VAGA_FILA)
            horas_restantes = max(0.0, (prazo_limite - now).total_seconds() / 3600.0)

        resultado.append({
            "posicao": idx,
            "matricula_id": m.id,
            "aluno_id": m.aluno.id,
            "aluno_nome": m.aluno.nome,
            "aluno_categoria": m.aluno.categoria,
            "data_solicitacao": m.data,
            "estado": m.estado,
            "data_oferta_vaga": m.data_oferta_vaga,
            "prazo_limite_confirmacao": prazo_limite,
            "horas_restantes": round(horas_restantes, 2) if horas_restantes is not None else None,
        })

    return resultado


def solicitar_matricula(db: Session, aluno_id: int, turma_id: int) -> Matricula:
    """
    Aplica todas as regras de solicitação de matrícula:
    - Regra 1: Aluno ativo, aprovado nos pré-requisitos, limite de créditos por categoria.
    - Regra 3: Reprovação 3x na mesma disciplina impede matrícula.
    - Regra 6: Conflito de horários com turmas já confirmadas é negado.
    - Regra 2: Se lotada, entra na lista de espera.
    """
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

    if turma.estado in [EstadoTurma.CANCELADA, EstadoTurma.ENCERRADA]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não é possível solicitar matrícula em turma {turma.estado.value}."
        )

    # Verificar se o aluno já possui matrícula ativa nesta turma ou na mesma disciplina no mesmo semestre
    matricula_existente = db.query(Matricula).join(Turma).filter(
        Matricula.aluno_id == aluno_id,
        Turma.semestre == turma.semestre,
        Turma.disciplina_id == turma.disciplina_id,
        Matricula.estado.in_([EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA, EstadoMatricula.LISTA_DE_ESPERA])
    ).first()

    if matricula_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Aluno já possui matrícula ativa ({matricula_existente.estado.value}) nesta disciplina para o semestre {turma.semestre}."
        )

    # Regra 1: A matrícula só é permitida a aluno ativo
    if aluno.situacao != SituacaoAluno.ATIVO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Matrícula não permitida: aluno com situação '{aluno.situacao.value}'. Somente alunos ativos podem se matricular."
        )

    # Regra 3: Aluno reprovado três vezes na mesma disciplina fica impedido de se matricular nela novamente
    reprovacoes = count_reprovacoes_disciplina(db, aluno.id, turma.disciplina_id)
    if reprovacoes >= MAX_REPROVACOES_DISCIPLINA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aluno reprovado {reprovacoes} vezes na disciplina '{turma.disciplina.nome}'. Matrícula impedida por exceder o limite de 3 reprovações."
        )

    # Regra 1: ...que tenha sido aprovado em todos os pré-requisitos da disciplina segundo o histórico
    prereqs = db.query(PreRequisito).filter(PreRequisito.disciplina_id == turma.disciplina_id).all()
    prereqs_pendentes = []
    for p in prereqs:
        if not is_aprovado_na_disciplina(db, aluno.id, p.pre_requisito_id):
            prereqs_pendentes.append(f"{p.disciplina_requisito.codigo} - {p.disciplina_requisito.nome}")

    if prereqs_pendentes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aluno não cumpriu os seguintes pré-requisitos: {', '.join(prereqs_pendentes)}."
        )

    # Regra 1: ...e que não ultrapasse o máximo de créditos da sua categoria no semestre
    regras_cat = REGRAS_CATEGORIAS[aluno.categoria]
    creditos_atuais = calcular_creditos_aluno_semestre(db, aluno.id, turma.semestre)
    creditos_pretendidos = turma.disciplina.numero_creditos

    if creditos_atuais + creditos_pretendidos > regras_cat.max_creditos_semestre:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Limite de créditos da categoria '{aluno.categoria.value}' excedido. "
                f"Máximo permitido: {regras_cat.max_creditos_semestre}, "
                f"atual no semestre: {creditos_atuais}, "
                f"disciplina pretendida: {creditos_pretendidos}."
            )
        )

    # Regra 6: Matrícula em turma cujo horário conflita com outra turma já confirmada do aluno é negada
    verificar_conflito_horario(db, aluno.id, turma)

    # Regra 2: Se a turma estiver lotada, a matrícula entra em lista de espera
    # Antes, processa expirações se houver
    processar_expiracoes_e_fila(db, turma.id)

    ocupadas = count_vagas_ocupadas_turma(db, turma.id)
    if ocupadas < turma.numero_vagas:
        # Há vaga imediata disponível
        estado_inicial = EstadoMatricula.CONFIRMADA
        data_oferta = None
    else:
        # Turma lotada -> Lista de espera
        estado_inicial = EstadoMatricula.LISTA_DE_ESPERA
        data_oferta = None

    matricula = Matricula(
        aluno_id=aluno.id,
        turma_id=turma.id,
        data=datetime.now(timezone.utc),
        estado=estado_inicial,
        data_oferta_vaga=data_oferta,
    )
    db.add(matricula)
    db.commit()
    db.refresh(matricula)

    # Atualizar estado da turma
    ocupadas_apos = count_vagas_ocupadas_turma(db, turma.id)
    if ocupadas_apos >= turma.numero_vagas:
        turma.estado = EstadoTurma.LOTADA
        db.commit()

    return matricula


def confirmar_matricula(db: Session, matricula_id: int, simulated_now: Optional[datetime] = None) -> Matricula:
    """
    Confirma uma matrícula pendente (ex: quando o aluno é contemplado na lista de espera dentro de 48h).
    """
    now = get_current_time(simulated_now)
    matricula = get_matricula_by_id(db, matricula_id)

    if matricula.estado == EstadoMatricula.CONFIRMADA:
        return matricula

    if matricula.estado in [EstadoMatricula.CANCELADA, EstadoMatricula.TRANCADA]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Matrícula com estado '{matricula.estado.value}' não pode ser confirmada."
        )

    if matricula.estado == EstadoMatricula.LISTA_DE_ESPERA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Matrícula ainda está em lista de espera. Não há vaga liberada para confirmação."
        )

    # Se estiver em SOLICITADA (oferta de vaga liberada da fila)
    if matricula.estado == EstadoMatricula.SOLICITADA:
        if matricula.data_oferta_vaga:
            data_oferta = ensure_utc(matricula.data_oferta_vaga)
            if (now - data_oferta).total_seconds() > HORAS_EXPIRACAO_VAGA_FILA * 3600:
                matricula.estado = EstadoMatricula.CANCELADA
                db.commit()
                # Libera a vaga para o próximo
                processar_expiracoes_e_fila(db, matricula.turma_id, simulated_now)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Prazo de {HORAS_EXPIRACAO_VAGA_FILA} horas para confirmação expirou. Matrícula cancelada."
                )

        # Revalidar conflito de horário e créditos
        aluno = matricula.aluno
        if aluno.situacao != SituacaoAluno.ATIVO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Aluno não está mais ativo (situação: {aluno.situacao.value})."
            )

        verificar_conflito_horario(db, aluno.id, matricula.turma)

        regras_cat = REGRAS_CATEGORIAS[aluno.categoria]
        # Calcular créditos sem contar a própria matrícula se já contasse
        creditos_atuais = db.query(Matricula).join(Turma).filter(
            Matricula.aluno_id == aluno.id,
            Turma.semestre == matricula.turma.semestre,
            Matricula.id != matricula.id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        ).all()
        total_creditos = sum(m.turma.disciplina.numero_creditos for m in creditos_atuais)

        if total_creditos + matricula.turma.disciplina.numero_creditos > regras_cat.max_creditos_semestre:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Limite de créditos da categoria '{aluno.categoria.value}' excedido."
            )

        matricula.estado = EstadoMatricula.CONFIRMADA
        db.commit()
        db.refresh(matricula)

        # Checar se turma está cheia
        ocupadas = count_vagas_ocupadas_turma(db, matricula.turma_id)
        if ocupadas >= matricula.turma.numero_vagas:
            matricula.turma.estado = EstadoTurma.LOTADA
            db.commit()

        return matricula

    return matricula


def cancelar_matricula(db: Session, matricula_id: int, simulated_now: Optional[datetime] = None) -> Matricula:
    """
    Regra 4: O trancamento de uma disciplina só é permitido dentro do prazo de cancelamento da categoria...
    Fora do prazo, o cancelamento registra reprovação por falta no histórico.
    """
    now = get_current_time(simulated_now)
    matricula = get_matricula_by_id(db, matricula_id)

    if matricula.estado in [EstadoMatricula.CANCELADA, EstadoMatricula.TRANCADA]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Matrícula já está com estado '{matricula.estado.value}'."
        )

    estado_anterior = matricula.estado
    turma_id = matricula.turma_id
    aluno = matricula.aluno
    turma = matricula.turma

    # Se a matrícula estava CONFIRMADA, verificar se o cancelamento é fora do prazo
    if estado_anterior == EstadoMatricula.CONFIRMADA:
        regras_cat = REGRAS_CATEGORIAS[aluno.categoria]
        data_mat = ensure_utc(matricula.data)
        dias_decorridos = (now - data_mat).total_seconds() / 86400.0

        if dias_decorridos > regras_cat.prazo_cancelamento_dias:
            # Regra 4: Fora do prazo, o cancelamento registra reprovacao por falta no historico
            historico = Historico(
                aluno_id=aluno.id,
                disciplina_id=turma.disciplina_id,
                semestre=turma.semestre,
                nota=0.0,
                situacao=SituacaoHistorico.REPROVADO_POR_FALTA,
            )
            db.add(historico)

    matricula.estado = EstadoMatricula.CANCELADA
    db.commit()
    db.refresh(matricula)

    # Se liberou vaga de quem estava CONFIRMADA ou SOLICITADA, processa a fila
    if estado_anterior in [EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA]:
        processar_expiracoes_e_fila(db, turma_id, simulated_now)

    return matricula


def trancar_matricula(db: Session, matricula_id: int, simulated_now: Optional[datetime] = None) -> Matricula:
    """
    Regra 4:
    - O trancamento de uma disciplina só é permitido dentro do prazo de cancelamento da categoria
      e respeitando o limite de trancamentos.
    Regra 7:
    - Aluno que acumular três trancamentos no semestre passa à situação trancado,
      e todas as suas matrículas confirmadas são canceladas.
    """
    now = get_current_time(simulated_now)
    matricula = get_matricula_by_id(db, matricula_id)

    if matricula.estado != EstadoMatricula.CONFIRMADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Apenas matrículas confirmadas podem ser trancadas. Estado atual: '{matricula.estado.value}'."
        )

    aluno = matricula.aluno
    turma = matricula.turma
    regras_cat = REGRAS_CATEGORIAS[aluno.categoria]

    # Verificar prazo de cancelamento/trancamento da categoria
    data_mat = ensure_utc(matricula.data)
    dias_decorridos = (now - data_mat).total_seconds() / 86400.0
    if dias_decorridos > regras_cat.prazo_cancelamento_dias:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Prazo para trancamento expirado ({regras_cat.prazo_cancelamento_dias} dias "
                f"para categoria {aluno.categoria.value}). Dias decorridos: {int(dias_decorridos)}."
            )
        )

    # Verificar limite de trancamentos da categoria para a disciplina
    if regras_cat.max_trancamentos_disciplina == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aluno da categoria '{aluno.categoria.value}' não possui permissão para trancar disciplinas."
        )

    trancamentos_anteriores = count_trancamentos_disciplina(db, aluno.id, turma.disciplina_id)
    if trancamentos_anteriores >= regras_cat.max_trancamentos_disciplina:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Limite de trancamentos atingido para a disciplina '{turma.disciplina.nome}'. "
                f"Máximo permitido para {aluno.categoria.value}: {regras_cat.max_trancamentos_disciplina}."
            )
        )

    # Efetuar o trancamento
    matricula.estado = EstadoMatricula.TRANCADA
    
    # Registrar no histórico como TRANCADO
    historico = Historico(
        aluno_id=aluno.id,
        disciplina_id=turma.disciplina_id,
        semestre=turma.semestre,
        nota=None,
        situacao=SituacaoHistorico.TRANCADO,
    )
    db.add(historico)
    db.commit()
    db.refresh(matricula)

    # Regra 7: Aluno que acumular três trancamentos no semestre passa à situação trancado,
    # e todas as suas matrículas confirmadas são canceladas.
    trancamentos_no_semestre = count_trancamentos_semestre(db, aluno.id, turma.semestre)
    if trancamentos_no_semestre >= MAX_TRANCAMENTOS_SEMESTRE_ALUNO:
        aluno.situacao = SituacaoAluno.TRANCADO
        db.commit()

        # Cancelar todas as outras matrículas confirmadas do aluno no semestre
        outras_matriculas = db.query(Matricula).join(Turma).filter(
            Matricula.aluno_id == aluno.id,
            Turma.semestre == turma.semestre,
            Matricula.id != matricula.id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        ).all()

        for m in outras_matriculas:
            m.estado = EstadoMatricula.CANCELADA
            db.commit()
            # Processar fila para cada uma dessas turmas
            processar_expiracoes_e_fila(db, m.turma_id, simulated_now)

    # Processar fila da turma desta matrícula recém-trancada
    processar_expiracoes_e_fila(db, turma.id, simulated_now)

    return matricula
