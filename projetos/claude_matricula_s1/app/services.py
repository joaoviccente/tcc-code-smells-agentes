"""Regras de negocio de matricula.

As funcoes deste modulo apenas fazem flush; o commit fica a cargo da camada HTTP,
de modo que cada requisicao seja uma transacao atomica.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.clock import agora
from app.enums import EstadoMatricula as EM
from app.enums import EstadoTurma as ET
from app.enums import SituacaoAluno, SituacaoHistorico
from app.errors import ErroNegocio, nao_encontrado
from app.models import Aluno, Historico, Matricula, PreRequisito, Turma

OCUPA_VAGA = (EM.SOLICITADA, EM.CONFIRMADA)
ATIVAS = (EM.SOLICITADA, EM.CONFIRMADA, EM.LISTA_DE_ESPERA)
TURMA_FECHADA = (ET.CANCELADA, ET.ENCERRADA)


# ---------------------------------------------------------------- utilitarios
def obter(db: Session, modelo, id_: int, nome: str):
    obj = db.get(modelo, id_)
    if obj is None:
        raise nao_encontrado(nome, id_)
    return obj


def ocupacao(db: Session, turma: Turma) -> int:
    return db.scalar(
        select(func.count()).select_from(Matricula)
        .where(Matricula.turma_id == turma.id, Matricula.estado.in_(OCUPA_VAGA))
    )


def atualizar_estado_turma(db: Session, turma: Turma) -> None:
    if turma.estado in TURMA_FECHADA:
        return
    turma.estado = ET.LOTADA if ocupacao(db, turma) >= turma.vagas else ET.ABERTA


def fila_espera(db: Session, turma: Turma) -> list[Matricula]:
    """Regra 2: ordena pela prioridade da categoria e, no empate, pela data da solicitacao."""
    itens = db.scalars(
        select(Matricula).where(Matricula.turma_id == turma.id, Matricula.estado == EM.LISTA_DE_ESPERA)
    ).all()
    return sorted(
        itens,
        key=lambda m: (-config.regras(m.aluno.categoria).prioridade_lista_espera, m.data, m.id),
    )


def preencher_vagas(db: Session, turma: Turma, inicio: datetime | None = None) -> None:
    """Oferece vagas livres aos primeiros da fila, que passam a ter 48h para confirmar.

    A matricula ofertada vai para 'solicitada' com prazo_confirmacao, reservando a vaga.
    """
    db.flush()
    if turma.estado in TURMA_FECHADA:
        return
    inicio = inicio or agora()
    while ocupacao(db, turma) < turma.vagas:
        fila = fila_espera(db, turma)
        if not fila:
            break
        prox = fila[0]
        if prox.aluno.situacao != SituacaoAluno.ATIVO:
            prox.estado = EM.CANCELADA
            prox.observacao = "Cancelada: aluno nao esta ativo no momento da oferta de vaga"
        else:
            prox.estado = EM.SOLICITADA
            prox.prazo_confirmacao = inicio + config.PRAZO_CONFIRMACAO_LISTA_ESPERA
            prox.observacao = "Vaga liberada: confirmar ate o prazo de confirmacao"
        db.flush()
    atualizar_estado_turma(db, turma)
    db.flush()


def processar_prazos(db: Session) -> int:
    """Regra 2: cancela ofertas de vaga nao confirmadas em 48h e passa a vez ao proximo.

    Processa em ordem cronologica; a oferta ao proximo comeca no instante em que a
    anterior expirou (por isso o processamento tardio produz o mesmo resultado).
    """
    total = 0
    while True:
        m = db.scalars(
            select(Matricula)
            .where(Matricula.estado == EM.SOLICITADA,
                   Matricula.prazo_confirmacao.is_not(None),
                   Matricula.prazo_confirmacao < agora())
            .order_by(Matricula.prazo_confirmacao, Matricula.id)
            .limit(1)
        ).first()
        if m is None:
            break
        m.estado = EM.CANCELADA
        m.observacao = "Cancelada: prazo de 48h para confirmacao esgotado"
        total += 1
        preencher_vagas(db, m.turma, inicio=m.prazo_confirmacao)
    db.flush()
    return total


def creditos_no_semestre(db: Session, aluno: Aluno, semestre: str, excluir_id: int | None = None) -> int:
    total = 0
    for m in aluno.matriculas:
        if m.id != excluir_id and m.estado in OCUPA_VAGA and m.turma.semestre == semestre:
            total += m.turma.disciplina.creditos
    return total


def conflito_horario(aluno: Aluno, turma: Turma, excluir_id: int | None = None) -> Turma | None:
    """Regra 6: retorna a turma confirmada do aluno que conflita com 'turma', se houver."""
    for m in aluno.matriculas:
        if m.id == excluir_id or m.estado != EM.CONFIRMADA:
            continue
        outra = m.turma
        if outra.id == turma.id or outra.semestre != turma.semestre:
            continue
        if any(h1.conflita(h2) for h1 in turma.horarios for h2 in outra.horarios):
            return outra
    return None


def contar_historico(db: Session, aluno_id: int, situacao: SituacaoHistorico,
                     disciplina_id: int | None = None, semestre: str | None = None) -> int:
    q = select(func.count()).select_from(Historico).where(
        Historico.aluno_id == aluno_id, Historico.situacao == situacao)
    if disciplina_id is not None:
        q = q.where(Historico.disciplina_id == disciplina_id)
    if semestre is not None:
        q = q.where(Historico.semestre == semestre)
    return db.scalar(q)


def _exigir_ativo(aluno: Aluno) -> None:
    if aluno.situacao != SituacaoAluno.ATIVO:
        raise ErroNegocio(403, "aluno_inativo",
                          f"Aluno em situacao '{aluno.situacao.value}' nao pode se matricular")


def _validar_creditos(db: Session, aluno: Aluno, turma: Turma, excluir_id: int | None = None) -> None:
    limite = config.regras(aluno.categoria).max_creditos_semestre
    usados = creditos_no_semestre(db, aluno, turma.semestre, excluir_id)
    novos = turma.disciplina.creditos
    if usados + novos > limite:
        raise ErroNegocio(
            422, "limite_creditos_excedido",
            f"Limite de {limite} creditos por semestre para categoria '{aluno.categoria.value}' "
            f"seria excedido ({usados} ja matriculados + {novos})",
            {"limite": limite, "creditos_atuais": usados, "creditos_disciplina": novos},
        )


def _validar_conflito(aluno: Aluno, turma: Turma, excluir_id: int | None = None) -> None:
    outra = conflito_horario(aluno, turma, excluir_id)
    if outra is not None:
        raise ErroNegocio(409, "conflito_horario",
                          f"Horario conflita com a turma {outra.id} ({outra.disciplina.codigo}) ja confirmada",
                          {"turma_conflitante_id": outra.id})


def _fim_prazo_cancelamento(m: Matricula) -> datetime:
    base = m.data_confirmacao or m.data
    return base + timedelta(days=config.regras(m.aluno.categoria).prazo_cancelamento_dias)


# ----------------------------------------------------------------- operacoes
def solicitar(db: Session, aluno_id: int, turma_id: int) -> Matricula:
    processar_prazos(db)
    aluno = obter(db, Aluno, aluno_id, "aluno")
    turma = obter(db, Turma, turma_id, "turma")
    disciplina = turma.disciplina

    # Regra 1: aluno ativo
    _exigir_ativo(aluno)

    if turma.estado in TURMA_FECHADA:
        raise ErroNegocio(409, "turma_indisponivel", f"Turma em estado '{turma.estado.value}'")

    duplicada = db.scalars(
        select(Matricula).join(Turma)
        .where(Matricula.aluno_id == aluno.id, Matricula.estado.in_(ATIVAS),
               Turma.disciplina_id == disciplina.id, Turma.semestre == turma.semestre)
    ).first()
    if duplicada is not None:
        raise ErroNegocio(409, "matricula_duplicada",
                          f"Aluno ja possui matricula {duplicada.id} ativa nesta disciplina no semestre",
                          {"matricula_id": duplicada.id})

    # Regra 3: tres reprovacoes na mesma disciplina
    reprovacoes = contar_historico(db, aluno.id, SituacaoHistorico.REPROVADO, disciplina.id)
    if reprovacoes >= config.MAX_REPROVACOES_POR_DISCIPLINA:
        raise ErroNegocio(403, "aluno_impedido_reprovacoes",
                          f"Aluno reprovado {reprovacoes} vezes em {disciplina.codigo}; "
                          f"matricula nesta disciplina nao e mais permitida")

    # Regra 1: pre-requisitos aprovados no historico
    exigidos = db.scalars(select(PreRequisito).where(PreRequisito.disciplina_id == disciplina.id)).all()
    aprovadas = set(db.scalars(
        select(Historico.disciplina_id).where(Historico.aluno_id == aluno.id,
                                              Historico.situacao == SituacaoHistorico.APROVADO)
    ).all())
    faltantes = [p.requisito.codigo for p in exigidos if p.requisito_id not in aprovadas]
    if faltantes:
        raise ErroNegocio(422, "pre_requisitos_pendentes",
                          "Aluno nao foi aprovado em todos os pre-requisitos",
                          {"pre_requisitos_pendentes": faltantes})

    # Regra 1: limite de creditos da categoria no semestre
    _validar_creditos(db, aluno, turma)

    # Regra 6: conflito com turma ja confirmada
    _validar_conflito(aluno, turma)

    # Regra 2: turma lotada -> lista de espera
    tem_vaga = ocupacao(db, turma) < turma.vagas and not fila_espera(db, turma)
    m = Matricula(aluno=aluno, turma=turma, data=agora(),
                  estado=EM.SOLICITADA if tem_vaga else EM.LISTA_DE_ESPERA)
    db.add(m)
    db.flush()
    atualizar_estado_turma(db, turma)
    db.flush()
    return m


def confirmar(db: Session, matricula_id: int) -> Matricula:
    processar_prazos(db)
    m = obter(db, Matricula, matricula_id, "matricula")
    if m.estado == EM.LISTA_DE_ESPERA:
        raise ErroNegocio(409, "aguardando_vaga", "Matricula em lista de espera; aguarde a liberacao de vaga")
    if m.estado != EM.SOLICITADA:
        raise ErroNegocio(409, "estado_invalido",
                          f"Somente matriculas solicitadas podem ser confirmadas (estado atual: '{m.estado.value}')")
    if m.turma.estado in TURMA_FECHADA:
        raise ErroNegocio(409, "turma_indisponivel", f"Turma em estado '{m.turma.estado.value}'")
    _exigir_ativo(m.aluno)
    _validar_conflito(m.aluno, m.turma, excluir_id=m.id)
    _validar_creditos(db, m.aluno, m.turma, excluir_id=m.id)
    m.estado = EM.CONFIRMADA
    m.data_confirmacao = agora()
    m.prazo_confirmacao = None
    m.observacao = None
    db.flush()
    return m


def cancelar(db: Session, matricula_id: int) -> tuple[Matricula, bool]:
    """Regra 4: cancelamento fora do prazo da categoria registra reprovacao por falta."""
    processar_prazos(db)
    m = obter(db, Matricula, matricula_id, "matricula")
    if m.estado in (EM.CANCELADA, EM.TRANCADA):
        raise ErroNegocio(409, "estado_invalido", f"Matricula ja esta '{m.estado.value}'")

    reprovacao = False
    if m.estado == EM.CONFIRMADA and agora() > _fim_prazo_cancelamento(m):
        reprovacao = True
        db.add(Historico(aluno_id=m.aluno_id, disciplina_id=m.turma.disciplina_id, semestre=m.turma.semestre,
                         nota=0.0, situacao=SituacaoHistorico.REPROVADO, matricula_id=m.id,
                         observacao="Reprovacao por falta (cancelamento fora do prazo)"))
    m.estado = EM.CANCELADA
    m.prazo_confirmacao = None
    m.observacao = ("Cancelada fora do prazo: reprovacao por falta registrada" if reprovacao
                    else "Cancelada pelo aluno")
    db.flush()
    preencher_vagas(db, m.turma)
    return m, reprovacao


def trancar(db: Session, matricula_id: int) -> Matricula:
    processar_prazos(db)
    m = obter(db, Matricula, matricula_id, "matricula")
    if m.estado != EM.CONFIRMADA:
        raise ErroNegocio(409, "estado_invalido",
                          f"Somente matriculas confirmadas podem ser trancadas (estado atual: '{m.estado.value}')")
    aluno, turma = m.aluno, m.turma
    r = config.regras(aluno.categoria)

    # Regra 4: dentro do prazo de cancelamento da categoria
    if agora() > _fim_prazo_cancelamento(m):
        raise ErroNegocio(422, "prazo_trancamento_esgotado",
                          f"Prazo de {r.prazo_cancelamento_dias} dias para categoria '{aluno.categoria.value}' "
                          f"esgotado; o cancelamento agora registrara reprovacao por falta")

    # Regra 4: limite de trancamentos por disciplina
    feitos = contar_historico(db, aluno.id, SituacaoHistorico.TRANCADO, turma.disciplina_id)
    if feitos >= r.max_trancamentos_por_disciplina:
        raise ErroNegocio(422, "limite_trancamentos_excedido",
                          f"Categoria '{aluno.categoria.value}' permite {r.max_trancamentos_por_disciplina} "
                          f"trancamento(s) por disciplina; aluno ja possui {feitos}",
                          {"limite": r.max_trancamentos_por_disciplina, "trancamentos": feitos})

    m.estado = EM.TRANCADA
    m.observacao = "Trancada pelo aluno"
    db.add(Historico(aluno_id=aluno.id, disciplina_id=turma.disciplina_id, semestre=turma.semestre,
                     nota=None, situacao=SituacaoHistorico.TRANCADO, matricula_id=m.id))
    db.flush()
    preencher_vagas(db, turma)

    # Regra 7: tres trancamentos no semestre -> aluno trancado e matriculas confirmadas canceladas
    no_semestre = contar_historico(db, aluno.id, SituacaoHistorico.TRANCADO, semestre=turma.semestre)
    if no_semestre >= config.MAX_TRANCAMENTOS_SEMESTRE:
        aluno.situacao = SituacaoAluno.TRANCADO
        afetadas = [x for x in aluno.matriculas if x.estado == EM.CONFIRMADA]
        for x in afetadas:
            x.estado = EM.CANCELADA
            x.observacao = f"Cancelada: aluno atingiu {config.MAX_TRANCAMENTOS_SEMESTRE} trancamentos no semestre"
        db.flush()
        for t in {x.turma for x in afetadas}:
            preencher_vagas(db, t)
    db.flush()
    return m


def cancelar_turma(db: Session, turma: Turma, motivo: str) -> int:
    """Cancela a turma e todas as suas matriculas. Retorna quantas matriculas mudaram de estado."""
    turma.estado = ET.CANCELADA
    n = 0
    for m in turma.matriculas:
        if m.estado != EM.CANCELADA:
            m.estado = EM.CANCELADA
            m.prazo_confirmacao = None
            m.observacao = motivo
            n += 1
    db.flush()
    return n


def encerrar_periodo_matricula(db: Session, semestre: str) -> dict:
    """Regra 5: turmas com menos de 5 matriculas confirmadas sao canceladas."""
    processar_prazos(db)
    turmas = db.scalars(
        select(Turma).where(Turma.semestre == semestre, Turma.estado.in_((ET.ABERTA, ET.LOTADA)))
        .order_by(Turma.id)
    ).all()
    canceladas, mantidas, total = [], [], 0
    for t in turmas:
        if t.confirmadas < config.MIN_MATRICULAS_CONFIRMADAS_TURMA:
            total += cancelar_turma(
                db, t, f"Turma cancelada: menos de {config.MIN_MATRICULAS_CONFIRMADAS_TURMA} "
                       f"matriculas confirmadas ao fim do periodo de matricula")
            canceladas.append(t.id)
        else:
            mantidas.append(t.id)
    db.flush()
    return {"semestre": semestre, "turmas_canceladas": canceladas, "turmas_mantidas": mantidas,
            "matriculas_canceladas": total}
