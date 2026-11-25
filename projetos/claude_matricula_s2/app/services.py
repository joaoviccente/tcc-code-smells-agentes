"""Regras de negocio de matricula, lista de espera, trancamento e encerramento de periodo."""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.errors import Conflito, NaoEncontrado, RegraNegocio
from app.models import (
    Aluno, Disciplina, EstadoMatricula as EM, EstadoTurma as ET, Historico, Matricula,
    PreRequisito, SituacaoAluno, SituacaoHistorico as SH, Turma,
)
from app.regras import (
    MAX_REPROVACOES_DISCIPLINA, MAX_TRANCAMENTOS_SEMESTRE, MIN_CONFIRMADAS_TURMA,
    PRAZO_CONFIRMACAO_FILA, REGRAS,
)

ATIVAS = (EM.SOLICITADA, EM.CONFIRMADA, EM.LISTA_DE_ESPERA)


# ------------------------------------------------------------------ utilitarios
def obter(db: Session, modelo, id_: int, nome: str):
    obj = db.get(modelo, id_)
    if obj is None:
        raise NaoEncontrado(f"{nome} {id_} nao encontrado(a)")
    return obj


def _tocar(m: Matricula, estado: EM, motivo: str | None = None):
    m.estado = estado
    m.data_atualizacao = clock.agora()
    if motivo is not None:
        m.motivo = motivo


def vagas_ocupadas(db: Session, turma: Turma) -> int:
    """Vagas em uso: solicitadas, confirmadas e vagas oferecidas a quem esta na fila."""
    db.flush()
    return db.scalar(
        select(func.count(Matricula.id)).where(
            Matricula.turma_id == turma.id,
            (Matricula.estado.in_([EM.SOLICITADA, EM.CONFIRMADA]))
            | ((Matricula.estado == EM.LISTA_DE_ESPERA) & Matricula.prazo_confirmacao.is_not(None)),
        )
    ) or 0


def fila_ordenada(db: Session, turma: Turma) -> list[Matricula]:
    """Fila da turma: prioridade da categoria e, no empate, data da solicitacao."""
    db.flush()
    itens = db.scalars(
        select(Matricula).where(Matricula.turma_id == turma.id, Matricula.estado == EM.LISTA_DE_ESPERA)
    ).all()
    return sorted(itens, key=lambda m: (REGRAS[m.aluno.categoria].prioridade_fila, m.data, m.id))


def posicao_na_fila(db: Session, m: Matricula) -> int | None:
    if m.estado != EM.LISTA_DE_ESPERA:
        return None
    for i, item in enumerate(fila_ordenada(db, m.turma), start=1):
        if item.id == m.id:
            return i
    return None


def atualizar_estado_turma(db: Session, turma: Turma):
    if turma.estado in (ET.CANCELADA, ET.ENCERRADA):
        return
    turma.estado = ET.LOTADA if vagas_ocupadas(db, turma) >= turma.vagas else ET.ABERTA


def preencher_vagas(db: Session, turma: Turma):
    """Oferece vagas livres aos primeiros da fila; cada um tem 48h para confirmar."""
    if turma.estado in (ET.CANCELADA, ET.ENCERRADA):
        return
    livres = turma.vagas - vagas_ocupadas(db, turma)
    if livres > 0:
        agora = clock.agora()
        for m in [m for m in fila_ordenada(db, turma) if m.prazo_confirmacao is None][:livres]:
            m.prazo_confirmacao = agora + PRAZO_CONFIRMACAO_FILA
            m.data_atualizacao = agora
    atualizar_estado_turma(db, turma)


def processar_expiracoes(db: Session, turma: Turma) -> int:
    """Cancela ofertas da fila com prazo de 48h esgotado e passa a vez ao proximo."""
    agora = clock.agora()
    total = 0
    while True:
        db.flush()
        expiradas = db.scalars(
            select(Matricula).where(
                Matricula.turma_id == turma.id,
                Matricula.estado == EM.LISTA_DE_ESPERA,
                Matricula.prazo_confirmacao.is_not(None),
                Matricula.prazo_confirmacao < agora,
            )
        ).all()
        if not expiradas:
            break
        for m in expiradas:
            _tocar(m, EM.CANCELADA, "prazo de 48h para confirmacao da vaga esgotado")
        total += len(expiradas)
        preencher_vagas(db, turma)
    return total


def processar_todas_expiracoes(db: Session) -> int:
    turma_ids = db.scalars(
        select(Matricula.turma_id).where(
            Matricula.estado == EM.LISTA_DE_ESPERA,
            Matricula.prazo_confirmacao.is_not(None),
            Matricula.prazo_confirmacao < clock.agora(),
        ).distinct()
    ).all()
    total = sum(processar_expiracoes(db, db.get(Turma, tid)) for tid in turma_ids)
    db.commit()
    return total


# ------------------------------------------------------------------ verificacoes
def _creditos_no_semestre(db: Session, aluno: Aluno, semestre: str, excluir_id: int | None = None) -> int:
    q = (
        select(func.coalesce(func.sum(Disciplina.creditos), 0))
        .select_from(Matricula).join(Turma, Matricula.turma_id == Turma.id)
        .join(Disciplina, Turma.disciplina_id == Disciplina.id)
        .where(Matricula.aluno_id == aluno.id, Turma.semestre == semestre, Matricula.estado.in_(ATIVAS))
    )
    if excluir_id is not None:
        q = q.where(Matricula.id != excluir_id)
    return db.scalar(q)


def horarios_conflitam(h1: list[dict], h2: list[dict]) -> bool:
    return any(
        a["dia"] == b["dia"] and a["inicio"] < b["fim"] and b["inicio"] < a["fim"] for a in h1 for b in h2
    )


def _verificar_conflito_horario(db: Session, aluno: Aluno, turma: Turma, excluir_id: int | None = None):
    confirmadas = db.scalars(
        select(Matricula).join(Turma, Matricula.turma_id == Turma.id).where(
            Matricula.aluno_id == aluno.id,
            Matricula.estado == EM.CONFIRMADA,
            Turma.semestre == turma.semestre,
            Matricula.id != (excluir_id or 0),
        )
    ).all()
    for m in confirmadas:
        if horarios_conflitam(turma.horario, m.turma.horario):
            raise Conflito(
                f"horario conflita com a turma {m.turma_id} ({m.turma.disciplina.codigo}) ja confirmada"
            )


def _verificar_creditos(db: Session, aluno: Aluno, turma: Turma, excluir_id: int | None = None):
    limite = REGRAS[aluno.categoria].max_creditos_semestre
    atual = _creditos_no_semestre(db, aluno, turma.semestre, excluir_id)
    if atual + turma.disciplina.creditos > limite:
        raise RegraNegocio(
            f"limite de {limite} creditos por semestre para categoria {aluno.categoria.value} excedido "
            f"(ja comprometidos: {atual}, disciplina: {turma.disciplina.creditos})"
        )


def _verificar_aluno_ativo(aluno: Aluno):
    if aluno.situacao != SituacaoAluno.ATIVO:
        raise RegraNegocio(f"aluno com situacao '{aluno.situacao.value}' nao pode se matricular")


# ------------------------------------------------------------------ operacoes
def solicitar(db: Session, aluno_id: int, turma_id: int) -> Matricula:
    aluno = obter(db, Aluno, aluno_id, "aluno")
    turma = obter(db, Turma, turma_id, "turma")
    if processar_expiracoes(db, turma):
        db.commit()

    _verificar_aluno_ativo(aluno)
    if turma.estado in (ET.CANCELADA, ET.ENCERRADA):
        raise Conflito(f"turma {turma.id} esta {turma.estado.value}")

    duplicada = db.scalar(
        select(Matricula.id).join(Turma, Matricula.turma_id == Turma.id).where(
            Matricula.aluno_id == aluno.id,
            Turma.disciplina_id == turma.disciplina_id,
            Turma.semestre == turma.semestre,
            Matricula.estado.in_(ATIVAS),
        )
    )
    if duplicada:
        raise Conflito(f"aluno ja possui matricula ativa ({duplicada}) nesta disciplina no semestre")

    # Regra 3: tres reprovacoes na mesma disciplina impedem nova matricula
    reprovacoes = db.scalar(
        select(func.count(Historico.id)).where(
            Historico.aluno_id == aluno.id,
            Historico.disciplina_id == turma.disciplina_id,
            Historico.situacao == SH.REPROVADO,
        )
    )
    if reprovacoes >= MAX_REPROVACOES_DISCIPLINA:
        raise RegraNegocio(
            f"aluno reprovado {reprovacoes} vezes nesta disciplina; nova matricula impedida"
        )

    # Regra 1: pre-requisitos aprovados segundo o historico
    requisitos = db.scalars(select(PreRequisito).where(PreRequisito.disciplina_id == turma.disciplina_id)).all()
    aprovadas = set(db.scalars(
        select(Historico.disciplina_id).where(Historico.aluno_id == aluno.id, Historico.situacao == SH.APROVADO)
    ).all())
    faltantes = [p.requisito.codigo for p in requisitos if p.requisito_id not in aprovadas]
    if faltantes:
        raise RegraNegocio(f"pre-requisitos nao cumpridos: {', '.join(sorted(faltantes))}")

    # Regra 1: limite de creditos da categoria; Regra 6: conflito de horario
    _verificar_creditos(db, aluno, turma)
    _verificar_conflito_horario(db, aluno, turma)

    # Regra 2: sem vaga -> lista de espera
    agora = clock.agora()
    tem_vaga = vagas_ocupadas(db, turma) < turma.vagas
    m = Matricula(
        aluno=aluno, turma=turma, data=agora, data_atualizacao=agora,
        estado=EM.SOLICITADA if tem_vaga else EM.LISTA_DE_ESPERA,
    )
    db.add(m)
    atualizar_estado_turma(db, turma)
    db.commit()
    db.refresh(m)
    return m


def confirmar(db: Session, matricula_id: int) -> Matricula:
    m = obter(db, Matricula, matricula_id, "matricula")
    if processar_expiracoes(db, m.turma):
        db.commit()

    if m.estado == EM.LISTA_DE_ESPERA and m.prazo_confirmacao is None:
        raise Conflito("matricula aguarda vaga na lista de espera e ainda nao pode ser confirmada")
    if m.estado not in (EM.SOLICITADA, EM.LISTA_DE_ESPERA):
        detalhe = f" ({m.motivo})" if m.motivo else ""
        raise Conflito(f"matricula no estado '{m.estado.value}' nao pode ser confirmada{detalhe}")
    if m.turma.estado in (ET.CANCELADA, ET.ENCERRADA):
        raise Conflito(f"turma {m.turma_id} esta {m.turma.estado.value}")

    _verificar_aluno_ativo(m.aluno)
    _verificar_creditos(db, m.aluno, m.turma, excluir_id=m.id)
    _verificar_conflito_horario(db, m.aluno, m.turma, excluir_id=m.id)

    _tocar(m, EM.CONFIRMADA)
    m.data_confirmacao = clock.agora()
    m.prazo_confirmacao = None
    atualizar_estado_turma(db, m.turma)
    db.commit()
    db.refresh(m)
    return m


def dentro_do_prazo(m: Matricula) -> bool:
    """Prazo de cancelamento da categoria, contado a partir da efetivacao da matricula."""
    base = m.data_confirmacao or m.data
    prazo = timedelta(days=REGRAS[m.aluno.categoria].prazo_cancelamento_dias)
    return clock.agora() - base <= prazo


def cancelar(db: Session, matricula_id: int) -> tuple[Matricula, bool]:
    m = obter(db, Matricula, matricula_id, "matricula")
    if processar_expiracoes(db, m.turma):
        db.commit()
    if m.estado not in ATIVAS:
        raise Conflito(f"matricula no estado '{m.estado.value}' nao pode ser cancelada")

    # Regra 4: cancelamento fora do prazo registra reprovacao por falta
    reprovacao = m.estado == EM.CONFIRMADA and not dentro_do_prazo(m)
    if reprovacao:
        db.add(Historico(
            aluno_id=m.aluno_id, disciplina_id=m.turma.disciplina_id, semestre=m.turma.semestre,
            nota=0.0, situacao=SH.REPROVADO, observacao="reprovacao por falta (cancelamento fora do prazo)",
        ))
    _tocar(m, EM.CANCELADA, "cancelada fora do prazo" if reprovacao else "cancelada pelo aluno")
    m.prazo_confirmacao = None
    preencher_vagas(db, m.turma)
    db.commit()
    db.refresh(m)
    return m, reprovacao


def trancar(db: Session, matricula_id: int) -> tuple[Matricula, int, bool]:
    m = obter(db, Matricula, matricula_id, "matricula")
    if m.estado != EM.CONFIRMADA:
        raise Conflito(f"apenas matriculas confirmadas podem ser trancadas (estado atual: '{m.estado.value}')")
    aluno = m.aluno
    regra = REGRAS[aluno.categoria]

    # Regra 4: prazo da categoria e limite de trancamentos por disciplina
    if regra.max_trancamentos_por_disciplina == 0:
        raise RegraNegocio(f"categoria {aluno.categoria.value} nao permite trancamento")
    if not dentro_do_prazo(m):
        raise RegraNegocio(
            f"prazo de {regra.prazo_cancelamento_dias} dias para trancamento esgotado; "
            "o cancelamento fora do prazo registra reprovacao por falta"
        )
    ja_trancadas = db.scalar(
        select(func.count(Historico.id)).where(
            Historico.aluno_id == aluno.id,
            Historico.disciplina_id == m.turma.disciplina_id,
            Historico.situacao == SH.TRANCADO,
        )
    )
    if ja_trancadas >= regra.max_trancamentos_por_disciplina:
        raise RegraNegocio(
            f"limite de {regra.max_trancamentos_por_disciplina} trancamento(s) por disciplina "
            f"da categoria {aluno.categoria.value} atingido"
        )

    _tocar(m, EM.TRANCADA, "trancada pelo aluno")
    db.add(Historico(
        aluno_id=aluno.id, disciplina_id=m.turma.disciplina_id, semestre=m.turma.semestre,
        nota=None, situacao=SH.TRANCADO, observacao="trancamento de disciplina",
    ))
    preencher_vagas(db, m.turma)
    db.flush()

    # Regra 7: tres trancamentos no semestre -> aluno trancado e matriculas canceladas
    no_semestre = db.scalar(
        select(func.count(Matricula.id)).join(Turma, Matricula.turma_id == Turma.id).where(
            Matricula.aluno_id == aluno.id, Matricula.estado == EM.TRANCADA, Turma.semestre == m.turma.semestre,
        )
    )
    aluno_trancado = no_semestre >= MAX_TRANCAMENTOS_SEMESTRE
    if aluno_trancado:
        aluno.situacao = SituacaoAluno.TRANCADO
        afetadas = db.scalars(
            select(Matricula).where(Matricula.aluno_id == aluno.id, Matricula.estado.in_(ATIVAS))
        ).all()
        turmas = {}
        for outra in afetadas:
            _tocar(outra, EM.CANCELADA,
                   f"aluno trancado ao atingir {MAX_TRANCAMENTOS_SEMESTRE} trancamentos no semestre")
            outra.prazo_confirmacao = None
            turmas[outra.turma_id] = outra.turma
        for t in turmas.values():
            preencher_vagas(db, t)

    db.commit()
    db.refresh(m)
    return m, no_semestre, aluno_trancado


def cancelar_turma(turma: Turma, motivo: str) -> int:
    turma.estado = ET.CANCELADA
    n = 0
    for m in turma.matriculas:
        if m.estado in ATIVAS:
            _tocar(m, EM.CANCELADA, motivo)
            m.prazo_confirmacao = None
            n += 1
    return n


def encerrar_periodo(db: Session, semestre: str) -> dict:
    """Regra 5: ao fim do periodo, turmas com menos de 5 confirmadas sao canceladas."""
    turmas = db.scalars(
        select(Turma).where(Turma.semestre == semestre, Turma.estado.in_([ET.ABERTA, ET.LOTADA]))
        .order_by(Turma.id)
    ).all()
    canceladas, mantidas, total = [], [], 0
    for t in turmas:
        processar_expiracoes(db, t)
        confirmadas = sum(1 for m in t.matriculas if m.estado == EM.CONFIRMADA)
        if confirmadas < MIN_CONFIRMADAS_TURMA:
            total += cancelar_turma(
                t, f"turma cancelada: menos de {MIN_CONFIRMADAS_TURMA} matriculas confirmadas ao fim do periodo"
            )
            canceladas.append(t.id)
        else:
            mantidas.append(t.id)
    db.commit()
    return {"semestre": semestre, "turmas_canceladas": canceladas, "turmas_mantidas": mantidas,
            "matriculas_canceladas": total}
