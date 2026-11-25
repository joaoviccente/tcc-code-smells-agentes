"""Regras de negocio de matricula."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import clock
from .enums import EstadoMatricula, EstadoTurma, SituacaoAluno, SituacaoHistorico
from .errors import Conflito, NaoEncontrado, RegraViolada
from .models import Aluno, Disciplina, Historico, Matricula, PreRequisito, Turma
from .regras import (
    LIMITE_REPROVACOES_DISCIPLINA,
    LIMITE_TRANCAMENTOS_SEMESTRE,
    MIN_MATRICULAS_CONFIRMADAS_TURMA,
    PRAZO_CONFIRMACAO_LISTA_ESPERA,
    REGRAS_CATEGORIA,
)

E = EstadoMatricula
OCUPAM_VAGA = (E.SOLICITADA, E.CONFIRMADA)
ATIVAS = (E.SOLICITADA, E.CONFIRMADA, E.LISTA_DE_ESPERA)
TURMA_FECHADA = (EstadoTurma.CANCELADA, EstadoTurma.ENCERRADA)


# ------------------------------------------------------------------ utilitarios
def obter_ou_404(db: Session, modelo, id_: int, rotulo: str):
    obj = db.get(modelo, id_)
    if obj is None:
        raise NaoEncontrado(f"{rotulo} {id_} nao encontrado(a).")
    return obj


def _minutos(v: str) -> int:
    h, m = v.split(":")[:2]
    return int(h) * 60 + int(m)


def horarios_conflitam(a: list[dict], b: list[dict]) -> bool:
    return any(
        x["dia"] == y["dia"]
        and _minutos(x["inicio"]) < _minutos(y["fim"])
        and _minutos(y["inicio"]) < _minutos(x["fim"])
        for x in a
        for y in b
    )


def contar_matriculas(db: Session, turma_id: int, estados) -> int:
    db.flush()
    return db.scalar(
        select(func.count(Matricula.id)).where(
            Matricula.turma_id == turma_id, Matricula.estado.in_(estados)
        )
    ) or 0


def fila_de_espera(db: Session, turma_id: int) -> list[Matricula]:
    """Fila ordenada por prioridade da categoria (desc) e data da solicitacao (asc)."""
    db.flush()
    pendentes = db.scalars(
        select(Matricula).where(
            Matricula.turma_id == turma_id, Matricula.estado == E.LISTA_DE_ESPERA
        )
    ).all()
    return sorted(
        pendentes,
        key=lambda m: (
            -REGRAS_CATEGORIA[m.aluno.categoria].peso_prioridade,
            m.data_solicitacao,
            m.id,
        ),
    )


def preencher_posicao(db: Session, matriculas: list[Matricula]) -> list[Matricula]:
    filas: dict[int, list[int]] = {}
    for m in matriculas:
        if m.estado == E.LISTA_DE_ESPERA:
            if m.turma_id not in filas:
                filas[m.turma_id] = [x.id for x in fila_de_espera(db, m.turma_id)]
            m.posicao_fila = filas[m.turma_id].index(m.id) + 1
        else:
            m.posicao_fila = None
    return matriculas


def atualizar_estado_turma(db: Session, turma: Turma) -> None:
    if turma.estado in TURMA_FECHADA:
        return
    ocupadas = contar_matriculas(db, turma.id, OCUPAM_VAGA)
    turma.estado = EstadoTurma.LOTADA if ocupadas >= turma.vagas else EstadoTurma.ABERTA


def preencher_vagas(db: Session, turma: Turma, inicio: datetime | None = None) -> list[Matricula]:
    """Oferece vagas livres aos primeiros da fila; cada um tem 48h para confirmar (regra 2)."""
    if turma.estado in TURMA_FECHADA:
        return []
    inicio = inicio or clock.agora()
    livres = turma.vagas - contar_matriculas(db, turma.id, OCUPAM_VAGA)
    promovidas: list[Matricula] = []
    for m in fila_de_espera(db, turma.id):
        if livres <= 0:
            break
        m.data_atualizacao = inicio
        if m.aluno.situacao != SituacaoAluno.ATIVO:
            m.estado = E.CANCELADA
            continue
        m.estado = E.SOLICITADA
        m.prazo_confirmacao = inicio + PRAZO_CONFIRMACAO_LISTA_ESPERA
        promovidas.append(m)
        livres -= 1
    atualizar_estado_turma(db, turma)
    return promovidas


def processar_expiracoes(db: Session) -> int:
    """Cancela vagas oferecidas da lista de espera nao confirmadas em 48h e passa a vez.

    A vez do proximo comeca no instante em que o prazo anterior expirou, de modo que o
    processamento tardio (sob demanda) produz o mesmo resultado de um agendador em tempo real.
    """
    agora = clock.agora()
    total = 0
    while True:
        m = db.scalars(
            select(Matricula)
            .where(
                Matricula.estado == E.SOLICITADA,
                Matricula.prazo_confirmacao.is_not(None),
                Matricula.prazo_confirmacao < agora,
            )
            .order_by(Matricula.prazo_confirmacao, Matricula.id)
            .limit(1)
        ).first()
        if m is None:
            break
        m.estado = E.CANCELADA
        m.data_atualizacao = m.prazo_confirmacao
        preencher_vagas(db, m.turma, inicio=m.prazo_confirmacao)
        total += 1
    if total:
        db.commit()
    return total


def creditos_no_semestre(db: Session, aluno_id: int, semestre: str, ignorar_id: int | None = None) -> int:
    q = (
        select(func.coalesce(func.sum(Disciplina.creditos), 0))
        .select_from(Matricula)
        .join(Turma, Matricula.turma_id == Turma.id)
        .join(Disciplina, Turma.disciplina_id == Disciplina.id)
        .where(
            Matricula.aluno_id == aluno_id,
            Turma.semestre == semestre,
            Matricula.estado.in_(ATIVAS),
        )
    )
    if ignorar_id is not None:
        q = q.where(Matricula.id != ignorar_id)
    return int(db.scalar(q) or 0)


def turma_em_conflito(db: Session, aluno_id: int, turma: Turma) -> Turma | None:
    """Regra 6: conflito com turmas ja confirmadas do aluno no mesmo semestre."""
    confirmadas = db.scalars(
        select(Matricula)
        .join(Turma, Matricula.turma_id == Turma.id)
        .where(
            Matricula.aluno_id == aluno_id,
            Matricula.estado == E.CONFIRMADA,
            Turma.semestre == turma.semestre,
            Turma.id != turma.id,
        )
    ).all()
    for m in confirmadas:
        if horarios_conflitam(m.turma.horario, turma.horario):
            return m.turma
    return None


def _contar_historico(db: Session, aluno_id: int, situacao: SituacaoHistorico, **filtros) -> int:
    q = select(func.count(Historico.id)).where(
        Historico.aluno_id == aluno_id, Historico.situacao == situacao
    )
    for campo, valor in filtros.items():
        q = q.where(getattr(Historico, campo) == valor)
    return db.scalar(q) or 0


def _exigir_aluno_ativo(aluno: Aluno) -> None:
    if aluno.situacao != SituacaoAluno.ATIVO:
        raise RegraViolada(
            "ALUNO_NAO_ATIVO",
            f"Aluno com situacao '{aluno.situacao.value}' nao pode se matricular.",
        )


def _exigir_turma_disponivel(turma: Turma) -> None:
    if turma.estado in TURMA_FECHADA:
        raise Conflito("TURMA_INDISPONIVEL", f"Turma {turma.id} esta {turma.estado.value}.")


def _verificar_creditos(db: Session, aluno: Aluno, turma: Turma, ignorar_id: int | None = None) -> None:
    maximo = REGRAS_CATEGORIA[aluno.categoria].max_creditos_semestre
    usados = creditos_no_semestre(db, aluno.id, turma.semestre, ignorar_id)
    pretendidos = usados + turma.disciplina.creditos
    if pretendidos > maximo:
        raise RegraViolada(
            "LIMITE_CREDITOS_EXCEDIDO",
            f"Limite de {maximo} creditos por semestre para a categoria "
            f"'{aluno.categoria.value}' seria excedido ({pretendidos}).",
            {"maximo": maximo, "em_uso": usados, "disciplina": turma.disciplina.creditos},
        )


def _verificar_conflito(db: Session, aluno: Aluno, turma: Turma) -> None:
    outra = turma_em_conflito(db, aluno.id, turma)
    if outra is not None:
        raise Conflito(
            "CONFLITO_HORARIO",
            f"Horario conflita com a turma {outra.id} ({outra.disciplina.codigo}) ja confirmada.",
            {"turma_conflitante_id": outra.id},
        )


def _dentro_prazo_cancelamento(m: Matricula, agora: datetime) -> bool:
    prazo = REGRAS_CATEGORIA[m.aluno.categoria].prazo_cancelamento_dias
    referencia = m.data_confirmacao or m.data_solicitacao
    return agora <= referencia + timedelta(days=prazo)


def _cancelar(m: Matricula, agora: datetime) -> None:
    m.estado = E.CANCELADA
    m.data_atualizacao = agora


# ------------------------------------------------------------------ operacoes
def solicitar_matricula(db: Session, aluno_id: int, turma_id: int) -> Matricula:
    aluno = obter_ou_404(db, Aluno, aluno_id, "Aluno")
    turma = obter_ou_404(db, Turma, turma_id, "Turma")
    disciplina = turma.disciplina

    _exigir_aluno_ativo(aluno)  # regra 1
    _exigir_turma_disponivel(turma)

    existente = db.scalar(
        select(Matricula)
        .join(Turma, Matricula.turma_id == Turma.id)
        .where(
            Matricula.aluno_id == aluno.id,
            Turma.disciplina_id == disciplina.id,
            Turma.semestre == turma.semestre,
            Matricula.estado.in_(ATIVAS + (E.TRANCADA,)),
        )
    )
    if existente is not None:
        raise Conflito(
            "MATRICULA_DUPLICADA",
            f"Aluno ja possui matricula ({existente.estado.value}) em {disciplina.codigo} "
            f"no semestre {turma.semestre}.",
            {"matricula_id": existente.id},
        )

    if _contar_historico(db, aluno.id, SituacaoHistorico.APROVADO, disciplina_id=disciplina.id):
        raise Conflito("DISCIPLINA_JA_APROVADA", f"Aluno ja foi aprovado em {disciplina.codigo}.")

    # regra 3
    reprovacoes = _contar_historico(db, aluno.id, SituacaoHistorico.REPROVADO, disciplina_id=disciplina.id)
    if reprovacoes >= LIMITE_REPROVACOES_DISCIPLINA:
        raise RegraViolada(
            "LIMITE_REPROVACOES",
            f"Aluno reprovado {reprovacoes} vezes em {disciplina.codigo} esta impedido de se matricular.",
        )

    # regra 1: pre-requisitos aprovados no historico
    requisitos = db.scalars(
        select(Disciplina)
        .join(PreRequisito, PreRequisito.requisito_id == Disciplina.id)
        .where(PreRequisito.disciplina_id == disciplina.id)
    ).all()
    aprovadas = set(
        db.scalars(
            select(Historico.disciplina_id).where(
                Historico.aluno_id == aluno.id,
                Historico.situacao == SituacaoHistorico.APROVADO,
            )
        ).all()
    )
    pendentes = sorted(r.codigo for r in requisitos if r.id not in aprovadas)
    if pendentes:
        raise RegraViolada(
            "PRE_REQUISITOS_PENDENTES",
            f"Pre-requisitos nao cumpridos: {', '.join(pendentes)}.",
            {"pendentes": pendentes},
        )

    _verificar_creditos(db, aluno, turma)  # regra 1
    _verificar_conflito(db, aluno, turma)  # regra 6

    # regra 2: sem vaga (ou com fila ja formada) -> lista de espera
    ha_vaga = contar_matriculas(db, turma.id, OCUPAM_VAGA) < turma.vagas
    fila_vazia = contar_matriculas(db, turma.id, (E.LISTA_DE_ESPERA,)) == 0
    agora = clock.agora()
    m = Matricula(
        aluno=aluno,
        turma=turma,
        data_solicitacao=agora,
        data_atualizacao=agora,
        estado=E.SOLICITADA if (ha_vaga and fila_vazia) else E.LISTA_DE_ESPERA,
    )
    db.add(m)
    atualizar_estado_turma(db, turma)
    db.commit()
    return preencher_posicao(db, [m])[0]


def confirmar_matricula(db: Session, matricula_id: int) -> Matricula:
    processar_expiracoes(db)
    m = obter_ou_404(db, Matricula, matricula_id, "Matricula")
    agora = clock.agora()
    if m.estado != E.SOLICITADA:
        if m.estado == E.CANCELADA and m.prazo_confirmacao and m.prazo_confirmacao < agora:
            raise Conflito(
                "PRAZO_CONFIRMACAO_EXPIRADO",
                "O prazo de 48 horas para confirmar a vaga expirou; a matricula foi cancelada.",
            )
        raise Conflito(
            "TRANSICAO_INVALIDA", f"Matricula no estado '{m.estado.value}' nao pode ser confirmada."
        )
    _exigir_aluno_ativo(m.aluno)
    _exigir_turma_disponivel(m.turma)
    _verificar_conflito(db, m.aluno, m.turma)
    _verificar_creditos(db, m.aluno, m.turma, ignorar_id=m.id)

    m.estado = E.CONFIRMADA
    m.data_confirmacao = agora
    m.data_atualizacao = agora
    m.prazo_confirmacao = None
    atualizar_estado_turma(db, m.turma)
    db.commit()
    return m


def cancelar_matricula(db: Session, matricula_id: int) -> tuple[Matricula, list[str]]:
    m = obter_ou_404(db, Matricula, matricula_id, "Matricula")
    if m.estado not in ATIVAS:
        raise Conflito(
            "TRANSICAO_INVALIDA", f"Matricula no estado '{m.estado.value}' nao pode ser cancelada."
        )
    agora = clock.agora()
    avisos: list[str] = []
    # regra 4: cancelamento fora do prazo registra reprovacao por falta
    if m.estado == E.CONFIRMADA and not _dentro_prazo_cancelamento(m, agora):
        db.add(
            Historico(
                aluno_id=m.aluno_id,
                disciplina_id=m.turma.disciplina_id,
                semestre=m.turma.semestre,
                nota=0.0,
                situacao=SituacaoHistorico.REPROVADO,
                por_falta=True,
            )
        )
        avisos.append("Cancelamento fora do prazo: reprovacao por falta registrada no historico.")
    ocupava_vaga = m.estado in OCUPAM_VAGA
    _cancelar(m, agora)
    if ocupava_vaga:
        for p in preencher_vagas(db, m.turma, agora):
            avisos.append(f"Vaga oferecida a matricula {p.id} da lista de espera.")
    db.commit()
    return m, avisos


def trancar_matricula(db: Session, matricula_id: int) -> tuple[Matricula, list[str]]:
    m = obter_ou_404(db, Matricula, matricula_id, "Matricula")
    if m.estado != E.CONFIRMADA:
        raise Conflito(
            "TRANSICAO_INVALIDA",
            f"Apenas matriculas confirmadas podem ser trancadas (estado atual: '{m.estado.value}').",
        )
    aluno = m.aluno
    regra = REGRAS_CATEGORIA[aluno.categoria]
    agora = clock.agora()

    if regra.max_trancamentos_por_disciplina == 0:
        raise RegraViolada(
            "TRANCAMENTO_NAO_PERMITIDO",
            f"Alunos da categoria '{aluno.categoria.value}' nao podem trancar disciplinas.",
        )
    if not _dentro_prazo_cancelamento(m, agora):
        raise RegraViolada(
            "PRAZO_TRANCAMENTO_EXPIRADO",
            f"Prazo de {regra.prazo_cancelamento_dias} dias para trancamento expirou. "
            "O cancelamento fora do prazo registra reprovacao por falta.",
        )
    disciplina_id = m.turma.disciplina_id
    trancamentos = _contar_historico(db, aluno.id, SituacaoHistorico.TRANCADO, disciplina_id=disciplina_id)
    if trancamentos >= regra.max_trancamentos_por_disciplina:
        raise RegraViolada(
            "LIMITE_TRANCAMENTOS_DISCIPLINA",
            f"Limite de {regra.max_trancamentos_por_disciplina} trancamento(s) por disciplina "
            f"atingido para a categoria '{aluno.categoria.value}'.",
        )

    semestre = m.turma.semestre
    m.estado = E.TRANCADA
    m.data_atualizacao = agora
    db.add(
        Historico(
            aluno_id=aluno.id,
            disciplina_id=disciplina_id,
            semestre=semestre,
            nota=None,
            situacao=SituacaoHistorico.TRANCADO,
        )
    )
    db.flush()
    avisos: list[str] = []
    turmas_afetadas = {m.turma.id: m.turma}

    # regra 7
    no_semestre = _contar_historico(db, aluno.id, SituacaoHistorico.TRANCADO, semestre=semestre)
    if no_semestre >= LIMITE_TRANCAMENTOS_SEMESTRE:
        aluno.situacao = SituacaoAluno.TRANCADO
        canceladas = 0
        for outra in aluno.matriculas:
            if outra.estado in ATIVAS:
                _cancelar(outra, agora)
                turmas_afetadas[outra.turma.id] = outra.turma
                canceladas += 1
        avisos.append(
            f"Aluno atingiu {no_semestre} trancamentos no semestre {semestre}: situacao alterada "
            f"para 'trancado' e {canceladas} matricula(s) cancelada(s)."
        )
    for turma in turmas_afetadas.values():
        preencher_vagas(db, turma, agora)
    db.commit()
    return m, avisos


def cancelar_turma(db: Session, turma: Turma) -> None:
    agora = clock.agora()
    turma.estado = EstadoTurma.CANCELADA
    for m in turma.matriculas:
        if m.estado != E.CANCELADA:
            _cancelar(m, agora)


def encerrar_turma(db: Session, turma: Turma) -> None:
    agora = clock.agora()
    turma.estado = EstadoTurma.ENCERRADA
    for m in turma.matriculas:
        if m.estado in (E.SOLICITADA, E.LISTA_DE_ESPERA):
            _cancelar(m, agora)


def encerrar_periodo_matricula(db: Session, semestre: str) -> tuple[list[int], list[int]]:
    """Regra 5: turmas com menos de 5 confirmadas sao canceladas com todas as matriculas."""
    turmas = db.scalars(
        select(Turma)
        .where(Turma.semestre == semestre, Turma.estado.in_((EstadoTurma.ABERTA, EstadoTurma.LOTADA)))
        .order_by(Turma.id)
    ).all()
    canceladas, mantidas = [], []
    for turma in turmas:
        if contar_matriculas(db, turma.id, (E.CONFIRMADA,)) < MIN_MATRICULAS_CONFIRMADAS_TURMA:
            cancelar_turma(db, turma)
            canceladas.append(turma.id)
        else:
            mantidas.append(turma.id)
    db.commit()
    return canceladas, mantidas
