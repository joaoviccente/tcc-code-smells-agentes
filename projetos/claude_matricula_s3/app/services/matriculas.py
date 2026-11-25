"""Regras de negócio de matrícula, lista de espera, trancamento e cancelamento."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import errors
from ..models import (
    Aluno,
    EstadoMatricula,
    EstadoTurma,
    Historico,
    Matricula,
    PeriodoMatricula,
    PreRequisito,
    SituacaoAluno,
    SituacaoHistorico,
    Turma,
)
from ..regras import (
    MAX_REPROVACOES_POR_DISCIPLINA,
    MAX_TRANCAMENTOS_SEMESTRE,
    MIN_CONFIRMADAS_POR_TURMA,
    PRAZO_CONFIRMACAO_LISTA_ESPERA,
    regra_do_aluno,
)

E = EstadoMatricula
# Matrículas que ainda "valem" no semestre (contam créditos, impedem duplicidade).
ESTADOS_ATIVOS = (E.solicitada, E.confirmada, E.lista_de_espera)
TURMA_EM_ANDAMENTO = (EstadoTurma.aberta, EstadoTurma.lotada)


# ====================================================================== consultas
def obter_matricula(db: Session, matricula_id: int) -> Matricula:
    m = db.get(Matricula, matricula_id)
    if m is None:
        raise errors.nao_encontrado("Matrícula", matricula_id)
    return m


def contar_confirmadas(db: Session, turma_id: int) -> int:
    return db.scalar(
        select(func.count(Matricula.id)).where(
            Matricula.turma_id == turma_id, Matricula.estado == E.confirmada
        )
    )


def contar_ocupadas(db: Session, turma_id: int) -> int:
    """Vagas ocupadas: solicitadas, confirmadas e ofertas pendentes da lista de espera."""
    return db.scalar(
        select(func.count(Matricula.id)).where(
            Matricula.turma_id == turma_id,
            (Matricula.estado.in_((E.solicitada, E.confirmada)))
            | ((Matricula.estado == E.lista_de_espera) & Matricula.prazo_confirmacao.is_not(None)),
        )
    )


def fila_de_espera(db: Session, turma_id: int) -> list[Matricula]:
    """Fila ordenada: quem já recebeu oferta de vaga primeiro; depois prioridade da
    categoria do aluno e, em empate, data da solicitação (regra 2)."""
    itens = db.scalars(
        select(Matricula)
        .join(Aluno)
        .where(Matricula.turma_id == turma_id, Matricula.estado == E.lista_de_espera)
    ).all()
    return sorted(
        itens,
        key=lambda m: (
            m.prazo_confirmacao is None,
            regra_do_aluno(m.aluno.categoria).prioridade_lista_espera,
            m.data,
            m.id,
        ),
    )


def posicao_na_fila(db: Session, m: Matricula) -> Optional[int]:
    if m.estado != E.lista_de_espera:
        return None
    for i, item in enumerate(fila_de_espera(db, m.turma_id), start=1):
        if item.id == m.id:
            return i
    return None


def _creditos_no_semestre(db: Session, aluno_id: int, semestre: str, excluir_id=None) -> int:
    from ..models import Disciplina

    q = (
        select(func.coalesce(func.sum(Disciplina.creditos), 0))
        .select_from(Matricula)
        .join(Turma, Matricula.turma_id == Turma.id)
        .join(Disciplina, Turma.disciplina_id == Disciplina.id)
        .where(
            Matricula.aluno_id == aluno_id,
            Turma.semestre == semestre,
            Matricula.estado.in_(ESTADOS_ATIVOS),
        )
    )
    if excluir_id is not None:
        q = q.where(Matricula.id != excluir_id)
    return db.scalar(q)


def _conflito_horario(db: Session, aluno_id: int, turma: Turma, excluir_id=None) -> Optional[Turma]:
    """Retorna a turma confirmada do aluno (mesmo semestre) que conflita com `turma`."""
    q = (
        select(Matricula)
        .join(Turma)
        .where(
            Matricula.aluno_id == aluno_id,
            Matricula.estado == E.confirmada,
            Turma.semestre == turma.semestre,
            Turma.id != turma.id,
        )
    )
    if excluir_id is not None:
        q = q.where(Matricula.id != excluir_id)
    for outra in db.scalars(q).all():
        for h1 in turma.horarios:
            for h2 in outra.turma.horarios:
                if h1.dia == h2.dia and h1.inicio < h2.fim and h2.inicio < h1.fim:
                    return outra.turma
    return None


def _contar_historico(db: Session, aluno_id: int, situacao: SituacaoHistorico, **filtros) -> int:
    q = select(func.count(Historico.id)).where(
        Historico.aluno_id == aluno_id, Historico.situacao == situacao
    )
    for campo, valor in filtros.items():
        q = q.where(getattr(Historico, campo) == valor)
    return db.scalar(q)


def _prazo_cancelamento_expirado(m: Matricula, agora: datetime) -> bool:
    regra = regra_do_aluno(m.aluno.categoria)
    inicio = m.data_confirmacao or m.data
    return agora > inicio + timedelta(days=regra.prazo_cancelamento_dias)


# ================================================================ estado de turma
def atualizar_estado_turma(db: Session, turma: Turma) -> None:
    if turma.estado in TURMA_EM_ANDAMENTO:
        db.flush()
        lotada = contar_ocupadas(db, turma.id) >= turma.vagas
        turma.estado = EstadoTurma.lotada if lotada else EstadoTurma.aberta


def ofertar_vagas_liberadas(db: Session, turma: Turma, agora: datetime) -> list[Matricula]:
    """Quando há vaga livre, o primeiro da fila recebe 48 h para confirmar (regra 2)."""
    ofertadas: list[Matricula] = []
    if turma.estado not in TURMA_EM_ANDAMENTO:
        return ofertadas
    db.flush()
    livres = turma.vagas - contar_ocupadas(db, turma.id)
    if livres > 0:
        aguardando = [m for m in fila_de_espera(db, turma.id) if m.prazo_confirmacao is None]
        for m in aguardando[:livres]:
            m.prazo_confirmacao = agora + PRAZO_CONFIRMACAO_LISTA_ESPERA
            ofertadas.append(m)
    atualizar_estado_turma(db, turma)
    return ofertadas


def _cancelar(m: Matricula, agora: datetime, motivo: str) -> None:
    m.estado = E.cancelada
    m.data_cancelamento = agora
    m.motivo_cancelamento = motivo
    m.prazo_confirmacao = None


def processar_expiracoes(db: Session, agora: datetime) -> int:
    """Cancela ofertas da lista de espera não confirmadas em 48 h e passa a vez ao próximo."""
    total = 0
    while True:
        expiradas = db.scalars(
            select(Matricula).where(
                Matricula.estado == E.lista_de_espera,
                Matricula.prazo_confirmacao.is_not(None),
                Matricula.prazo_confirmacao < agora,
            )
        ).all()
        if not expiradas:
            break
        turmas = {}
        for m in expiradas:
            _cancelar(m, agora, "Prazo de 48 horas para confirmar a vaga da lista de espera expirou.")
            turmas[m.turma_id] = m.turma
        for turma in turmas.values():
            ofertar_vagas_liberadas(db, turma, agora)
        total += len(expiradas)
    return total


# =================================================================== operações
@dataclass
class ResultadoOperacao:
    matricula: Matricula
    mensagem: str
    reprovacao_por_falta_registrada: bool = False
    aluno_trancado: bool = False
    matriculas_canceladas: list[int] = field(default_factory=list)


def solicitar(db: Session, aluno_id: int, turma_id: int, agora: datetime) -> ResultadoOperacao:
    aluno = db.get(Aluno, aluno_id)
    if aluno is None:
        raise errors.nao_encontrado("Aluno", aluno_id)
    turma = db.get(Turma, turma_id)
    if turma is None:
        raise errors.nao_encontrado("Turma", turma_id)
    disciplina = turma.disciplina
    regra = regra_do_aluno(aluno.categoria)

    periodo = db.get(PeriodoMatricula, turma.semestre)
    if periodo is not None and periodo.encerrado:
        raise errors.conflito(
            "PERIODO_MATRICULA_ENCERRADO",
            f"O período de matrícula do semestre {turma.semestre} está encerrado.",
        )
    if turma.estado not in TURMA_EM_ANDAMENTO:
        raise errors.conflito(
            "TURMA_INDISPONIVEL", f"A turma está {turma.estado.value} e não aceita matrículas."
        )

    # Regra 1: somente aluno ativo.
    if aluno.situacao != SituacaoAluno.ativo:
        raise errors.regra(
            "ALUNO_NAO_ATIVO",
            f"Apenas alunos ativos podem se matricular (situação atual: {aluno.situacao.value}).",
        )

    duplicada = db.scalar(
        select(Matricula.id)
        .join(Turma)
        .where(
            Matricula.aluno_id == aluno.id,
            Turma.disciplina_id == disciplina.id,
            Turma.semestre == turma.semestre,
            Matricula.estado.in_(ESTADOS_ATIVOS),
        )
    )
    if duplicada:
        raise errors.conflito(
            "MATRICULA_DUPLICADA",
            "O aluno já possui matrícula ativa nesta disciplina no semestre.",
            {"matricula_id": duplicada},
        )

    if _contar_historico(db, aluno.id, SituacaoHistorico.aprovado, disciplina_id=disciplina.id):
        raise errors.regra("DISCIPLINA_JA_APROVADA", "O aluno já foi aprovado nesta disciplina.")

    # Regra 3: três reprovações impedem nova matrícula.
    reprovacoes = _contar_historico(
        db, aluno.id, SituacaoHistorico.reprovado, disciplina_id=disciplina.id
    )
    if reprovacoes >= MAX_REPROVACOES_POR_DISCIPLINA:
        raise errors.regra(
            "LIMITE_REPROVACOES",
            f"Aluno reprovado {reprovacoes} vezes nesta disciplina; nova matrícula não permitida.",
        )

    # Regra 1: aprovação em todos os pré-requisitos.
    pendentes = []
    for pr in db.scalars(select(PreRequisito).where(PreRequisito.disciplina_id == disciplina.id)):
        if not _contar_historico(
            db, aluno.id, SituacaoHistorico.aprovado, disciplina_id=pr.requisito_id
        ):
            pendentes.append(pr.requisito.codigo)
    if pendentes:
        raise errors.regra(
            "PRE_REQUISITOS_PENDENTES",
            "O aluno não foi aprovado em todos os pré-requisitos da disciplina.",
            {"pendentes": sorted(pendentes)},
        )

    # Regra 1: limite de créditos da categoria no semestre.
    usados = _creditos_no_semestre(db, aluno.id, turma.semestre)
    if usados + disciplina.creditos > regra.max_creditos_semestre:
        raise errors.regra(
            "LIMITE_CREDITOS_EXCEDIDO",
            f"Limite de {regra.max_creditos_semestre} créditos por semestre para a categoria "
            f"{aluno.categoria.value} seria ultrapassado.",
            {
                "creditos_em_uso": usados,
                "creditos_disciplina": disciplina.creditos,
                "limite": regra.max_creditos_semestre,
            },
        )

    # Regra 6: conflito de horário com turma já confirmada.
    conflitante = _conflito_horario(db, aluno.id, turma)
    if conflitante is not None:
        raise errors.regra(
            "CONFLITO_HORARIO",
            "O horário da turma conflita com outra turma confirmada do aluno.",
            {"turma_conflitante_id": conflitante.id},
        )

    # Regra 2: turma lotada -> lista de espera.
    tem_vaga = contar_ocupadas(db, turma.id) < turma.vagas
    m = Matricula(
        aluno=aluno,
        turma=turma,
        data=agora,
        estado=E.solicitada if tem_vaga else E.lista_de_espera,
    )
    db.add(m)
    atualizar_estado_turma(db, turma)
    db.commit()
    msg = (
        "Matrícula solicitada; confirme para efetivá-la."
        if tem_vaga
        else "Turma lotada; matrícula incluída na lista de espera."
    )
    return ResultadoOperacao(m, msg)


def _exigir_turma_em_andamento(m: Matricula) -> None:
    if m.turma.estado not in TURMA_EM_ANDAMENTO:
        raise errors.conflito(
            "TURMA_INDISPONIVEL",
            f"A turma está {m.turma.estado.value}; a operação não é permitida.",
        )


def confirmar(db: Session, matricula_id: int, agora: datetime) -> ResultadoOperacao:
    m = obter_matricula(db, matricula_id)
    if m.estado == E.confirmada:
        raise errors.conflito("MATRICULA_JA_CONFIRMADA", "A matrícula já está confirmada.")
    if m.estado in (E.cancelada, E.trancada):
        raise errors.conflito(
            "ESTADO_INVALIDO", f"Matrícula {m.estado.value} não pode ser confirmada."
        )
    if m.estado == E.lista_de_espera and m.prazo_confirmacao is None:
        raise errors.conflito(
            "AGUARDANDO_VAGA",
            "A matrícula está na lista de espera e ainda não recebeu oferta de vaga.",
            {"posicao_lista_espera": posicao_na_fila(db, m)},
        )
    _exigir_turma_em_andamento(m)
    aluno, turma = m.aluno, m.turma
    if aluno.situacao != SituacaoAluno.ativo:
        raise errors.regra("ALUNO_NAO_ATIVO", "Apenas alunos ativos podem confirmar matrícula.")

    regra = regra_do_aluno(aluno.categoria)
    usados = _creditos_no_semestre(db, aluno.id, turma.semestre, excluir_id=m.id)
    if usados + turma.disciplina.creditos > regra.max_creditos_semestre:
        raise errors.regra(
            "LIMITE_CREDITOS_EXCEDIDO",
            f"Limite de {regra.max_creditos_semestre} créditos por semestre seria ultrapassado.",
        )
    conflitante = _conflito_horario(db, aluno.id, turma, excluir_id=m.id)
    if conflitante is not None:
        raise errors.regra(
            "CONFLITO_HORARIO",
            "O horário da turma conflita com outra turma confirmada do aluno.",
            {"turma_conflitante_id": conflitante.id},
        )

    m.estado = E.confirmada
    m.data_confirmacao = agora
    m.prazo_confirmacao = None
    atualizar_estado_turma(db, turma)
    db.commit()
    return ResultadoOperacao(m, "Matrícula confirmada.")


def cancelar(db: Session, matricula_id: int, agora: datetime) -> ResultadoOperacao:
    m = obter_matricula(db, matricula_id)
    if m.estado in (E.cancelada, E.trancada):
        raise errors.conflito(
            "ESTADO_INVALIDO", f"Matrícula {m.estado.value} não pode ser cancelada."
        )
    _exigir_turma_em_andamento(m)

    reprovacao = False
    # Regra 4: cancelamento de matrícula confirmada fora do prazo => reprovação por falta.
    if m.estado == E.confirmada and _prazo_cancelamento_expirado(m, agora):
        db.add(
            Historico(
                aluno_id=m.aluno_id,
                disciplina_id=m.turma.disciplina_id,
                semestre=m.turma.semestre,
                nota=0.0,
                situacao=SituacaoHistorico.reprovado,
                observacao="Reprovação por falta (cancelamento fora do prazo).",
                matricula_id=m.id,
            )
        )
        reprovacao = True

    _cancelar(
        m,
        agora,
        "Cancelada fora do prazo; reprovação por falta registrada."
        if reprovacao
        else "Cancelada a pedido do aluno.",
    )
    ofertar_vagas_liberadas(db, m.turma, agora)
    db.commit()
    msg = (
        "Matrícula cancelada fora do prazo; reprovação por falta registrada no histórico."
        if reprovacao
        else "Matrícula cancelada."
    )
    return ResultadoOperacao(m, msg, reprovacao_por_falta_registrada=reprovacao)


def trancar(db: Session, matricula_id: int, agora: datetime) -> ResultadoOperacao:
    m = obter_matricula(db, matricula_id)
    if m.estado != E.confirmada:
        raise errors.conflito(
            "ESTADO_INVALIDO", "Somente matrículas confirmadas podem ser trancadas."
        )
    _exigir_turma_em_andamento(m)
    aluno, turma = m.aluno, m.turma
    regra = regra_do_aluno(aluno.categoria)

    # Regra 4: limite de trancamentos por disciplina e prazo da categoria.
    if regra.max_trancamentos_por_disciplina == 0:
        raise errors.regra(
            "TRANCAMENTO_NAO_PERMITIDO",
            f"A categoria {aluno.categoria.value} não permite trancamento.",
        )
    if _prazo_cancelamento_expirado(m, agora):
        raise errors.regra(
            "PRAZO_TRANCAMENTO_EXPIRADO",
            f"O prazo de {regra.prazo_cancelamento_dias} dias para trancamento expirou.",
        )
    ja_trancadas = _contar_historico(
        db, aluno.id, SituacaoHistorico.trancado, disciplina_id=turma.disciplina_id
    )
    if ja_trancadas >= regra.max_trancamentos_por_disciplina:
        raise errors.regra(
            "LIMITE_TRANCAMENTOS_DISCIPLINA",
            f"Limite de {regra.max_trancamentos_por_disciplina} trancamento(s) nesta disciplina "
            "atingido.",
        )

    m.estado = E.trancada
    db.add(
        Historico(
            aluno_id=aluno.id,
            disciplina_id=turma.disciplina_id,
            semestre=turma.semestre,
            nota=None,
            situacao=SituacaoHistorico.trancado,
            observacao="Trancamento de disciplina.",
            matricula_id=m.id,
        )
    )
    ofertar_vagas_liberadas(db, turma, agora)

    # Regra 7: três trancamentos no semestre => aluno trancado e matrículas canceladas.
    resultado = ResultadoOperacao(m, "Matrícula trancada.")
    db.flush()
    if (
        _contar_historico(db, aluno.id, SituacaoHistorico.trancado, semestre=turma.semestre)
        >= MAX_TRANCAMENTOS_SEMESTRE
    ):
        aluno.situacao = SituacaoAluno.trancado
        afetadas = db.scalars(
            select(Matricula)
            .join(Turma)
            .where(
                Matricula.aluno_id == aluno.id,
                Matricula.estado.in_(ESTADOS_ATIVOS),
                Turma.estado.in_(TURMA_EM_ANDAMENTO),
            )
        ).all()
        for outra in afetadas:
            _cancelar(
                outra,
                agora,
                f"Aluno atingiu {MAX_TRANCAMENTOS_SEMESTRE} trancamentos no semestre.",
            )
            resultado.matriculas_canceladas.append(outra.id)
        for t in {o.turma_id: o.turma for o in afetadas}.values():
            ofertar_vagas_liberadas(db, t, agora)
        resultado.aluno_trancado = True
        resultado.mensagem = (
            f"Matrícula trancada. O aluno acumulou {MAX_TRANCAMENTOS_SEMESTRE} trancamentos no "
            "semestre, passou à situação 'trancado' e suas matrículas foram canceladas."
        )
    db.commit()
    return resultado


# ================================================================ turmas / período
def cancelar_turma(db: Session, turma: Turma, agora: datetime, motivo: str) -> int:
    turma.estado = EstadoTurma.cancelada
    n = 0
    for m in turma.matriculas:
        if m.estado != E.cancelada:
            _cancelar(m, agora, motivo)
            n += 1
    return n


def encerrar_turma(db: Session, turma: Turma, agora: datetime) -> None:
    if turma.estado not in TURMA_EM_ANDAMENTO:
        raise errors.conflito(
            "TURMA_INDISPONIVEL", f"A turma já está {turma.estado.value}."
        )
    turma.estado = EstadoTurma.encerrada
    for m in turma.matriculas:
        if m.estado in (E.solicitada, E.lista_de_espera):
            _cancelar(m, agora, "Turma encerrada sem confirmação da matrícula.")


def encerrar_periodo(db: Session, semestre: str, agora: datetime) -> dict:
    """Regra 5: ao fim do período, turmas com menos de 5 confirmadas são canceladas."""
    periodo = db.get(PeriodoMatricula, semestre)
    if periodo is not None and periodo.encerrado:
        raise errors.conflito(
            "PERIODO_JA_ENCERRADO", f"O período de matrícula de {semestre} já foi encerrado."
        )
    if periodo is None:
        periodo = PeriodoMatricula(semestre=semestre)
        db.add(periodo)

    canceladas, mantidas, total = [], [], 0
    turmas = db.scalars(
        select(Turma)
        .where(Turma.semestre == semestre, Turma.estado.in_(TURMA_EM_ANDAMENTO))
        .order_by(Turma.id)
    ).all()
    for turma in turmas:
        if contar_confirmadas(db, turma.id) < MIN_CONFIRMADAS_POR_TURMA:
            total += cancelar_turma(
                db,
                turma,
                agora,
                f"Turma cancelada: menos de {MIN_CONFIRMADAS_POR_TURMA} matrículas confirmadas "
                "ao fim do período de matrícula.",
            )
            canceladas.append(turma.id)
        else:
            mantidas.append(turma.id)

    periodo.encerrado = True
    periodo.data_encerramento = agora
    db.commit()
    return {
        "semestre": semestre,
        "turmas_canceladas": canceladas,
        "turmas_mantidas": mantidas,
        "matriculas_canceladas": total,
    }
