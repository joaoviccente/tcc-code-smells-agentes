"""Regras de negocio de matricula, lista de espera, trancamento e periodo."""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.errors import Conflito, NaoEncontrado, RegraViolada
from app.models import (Aluno, Disciplina, EstadoMatricula as EM, EstadoTurma as ET,
                        Historico, Matricula, PreRequisito, SituacaoAluno,
                        SituacaoHistorico as SH, Turma)
from app.regras import (MAX_REPROVACOES_DISCIPLINA, MAX_TRANCAMENTOS_SEMESTRE,
                        MIN_CONFIRMADAS_TURMA, PRAZO_CONFIRMACAO_LISTA_ESPERA,
                        REGRAS_CATEGORIA)

ESTADOS_ATIVOS = (EM.solicitada, EM.confirmada, EM.lista_de_espera)
TURMA_EM_OFERTA = (ET.aberta, ET.lotada)
MOTIVO_EXPIRACAO = "prazo de 48h para confirmacao da vaga expirado"


# ------------------------------------------------------------ utilitarios
def obter(db: Session, modelo, id_: int, nome: str, travar: bool = False):
    stmt = select(modelo).where(modelo.id == id_)
    if travar:
        stmt = stmt.with_for_update()  # efetivo em bancos com lock de linha
    obj = db.execute(stmt).scalar_one_or_none()
    if obj is None:
        raise NaoEncontrado(nome, id_)
    return obj


def _encerrar(m: Matricula, estado: EM, motivo: str, quando: Optional[datetime] = None):
    m.estado = estado
    m.prazo_confirmacao = None
    m.data_encerramento = quando or clock.agora()
    m.motivo_encerramento = motivo


def horarios_conflitam(h1: list, h2: list) -> bool:
    for a in h1:
        for b in h2:
            if a["dia"] == b["dia"] and a["inicio"] < b["fim"] and b["inicio"] < a["fim"]:
                return True
    return False


def prazo_cancelamento(m: Matricula) -> datetime:
    """Prazo contado a partir da confirmacao da matricula (ou da solicitacao)."""
    regra = REGRAS_CATEGORIA[m.aluno.categoria]
    base = m.data_confirmacao or m.data
    return base + timedelta(days=regra.prazo_cancelamento_dias)


# ------------------------------------------------------------ ocupacao
def vagas_ocupadas(db: Session, turma: Turma) -> int:
    """Solicitadas e confirmadas ocupam vaga; vaga oferecida a alguem da lista
    de espera fica reservada ate o fim do prazo de 48h."""
    db.flush()
    return db.scalar(
        select(func.count(Matricula.id)).where(
            Matricula.turma_id == turma.id,
            (Matricula.estado.in_([EM.solicitada, EM.confirmada]))
            | ((Matricula.estado == EM.lista_de_espera)
               & Matricula.prazo_confirmacao.is_not(None)),
        )
    ) or 0


def atualizar_estado_turma(db: Session, turma: Turma) -> None:
    if turma.estado in TURMA_EM_OFERTA:
        turma.estado = ET.lotada if vagas_ocupadas(db, turma) >= turma.vagas else ET.aberta


def fila_espera(db: Session, turma: Turma) -> list[Matricula]:
    """Ordenada por prioridade da categoria e, no empate, pela data da solicitacao."""
    db.flush()
    itens = db.scalars(
        select(Matricula).where(Matricula.turma_id == turma.id,
                                Matricula.estado == EM.lista_de_espera)
    ).all()
    return sorted(itens, key=lambda m: (
        REGRAS_CATEGORIA[m.aluno.categoria].prioridade_espera, m.data, m.id))


def liberar_vagas(db: Session, turma: Turma, inicio: Optional[datetime] = None) -> None:
    """Oferece cada vaga livre ao primeiro da fila, que tem 48h para confirmar."""
    if turma.estado not in TURMA_EM_OFERTA:
        return
    inicio = inicio or clock.agora()
    while vagas_ocupadas(db, turma) < turma.vagas:
        aguardando = [m for m in fila_espera(db, turma) if m.prazo_confirmacao is None]
        if not aguardando:
            break
        prox = aguardando[0]
        if prox.aluno.situacao != SituacaoAluno.ativo:
            _encerrar(prox, EM.cancelada, "aluno nao esta ativo", inicio)
            continue
        prox.prazo_confirmacao = inicio + PRAZO_CONFIRMACAO_LISTA_ESPERA
    atualizar_estado_turma(db, turma)


def processar_expiracoes(db: Session, turma: Turma) -> int:
    """Cancela ofertas de vaga cujo prazo de 48h expirou e repassa a vaga ao
    proximo da fila. O novo prazo conta do instante em que a vaga foi liberada
    (fim do prazo anterior), mesmo que o processamento ocorra depois."""
    agora = clock.agora()
    canceladas = 0
    while True:
        db.flush()
        expirada = db.scalars(
            select(Matricula).where(
                Matricula.turma_id == turma.id,
                Matricula.estado == EM.lista_de_espera,
                Matricula.prazo_confirmacao.is_not(None),
                Matricula.prazo_confirmacao <= agora,
            ).order_by(Matricula.prazo_confirmacao, Matricula.id)
        ).first()
        if expirada is None:
            break
        fim = expirada.prazo_confirmacao
        _encerrar(expirada, EM.cancelada, MOTIVO_EXPIRACAO, fim)
        canceladas += 1
        liberar_vagas(db, turma, inicio=fim)
    atualizar_estado_turma(db, turma)
    return canceladas


def processar_todas_expiracoes(db: Session) -> int:
    ids = db.scalars(
        select(Matricula.turma_id).where(
            Matricula.estado == EM.lista_de_espera,
            Matricula.prazo_confirmacao.is_not(None)).distinct()
    ).all()
    total = sum(processar_expiracoes(db, obter(db, Turma, i, "Turma")) for i in ids)
    db.commit()
    return total


def posicao_na_fila(db: Session, m: Matricula) -> Optional[int]:
    if m.estado != EM.lista_de_espera:
        return None
    for i, item in enumerate(fila_espera(db, m.turma), start=1):
        if item.id == m.id:
            return i
    return None


# ------------------------------------------------------------ validacoes
def _creditos_no_semestre(db: Session, aluno: Aluno, semestre: str) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(Disciplina.creditos), 0))
        .select_from(Matricula)
        .join(Turma, Turma.id == Matricula.turma_id)
        .join(Disciplina, Disciplina.id == Turma.disciplina_id)
        .where(Matricula.aluno_id == aluno.id, Turma.semestre == semestre,
               Matricula.estado.in_(ESTADOS_ATIVOS))
    ) or 0


def _contar_historico(db: Session, aluno_id: int, disciplina_id: int, situacao: SH) -> int:
    return db.scalar(
        select(func.count(Historico.id)).where(
            Historico.aluno_id == aluno_id, Historico.disciplina_id == disciplina_id,
            Historico.situacao == situacao)
    ) or 0


def _verificar_conflito_horario(db: Session, aluno: Aluno, turma: Turma) -> None:
    confirmadas = db.scalars(
        select(Matricula).join(Turma).where(
            Matricula.aluno_id == aluno.id, Matricula.estado == EM.confirmada,
            Turma.semestre == turma.semestre, Turma.id != turma.id)
    ).all()
    for m in confirmadas:
        if horarios_conflitam(turma.horario, m.turma.horario):
            raise RegraViolada(
                "CONFLITO_HORARIO",
                f"Horario conflita com a turma {m.turma.id} "
                f"({m.turma.disciplina.codigo}) ja confirmada",
                {"turma_conflitante_id": m.turma.id, "matricula_id": m.id})


def _verificar_aluno_ativo(aluno: Aluno) -> None:
    if aluno.situacao != SituacaoAluno.ativo:
        raise RegraViolada("ALUNO_NAO_ATIVO",
                           f"Aluno com situacao '{aluno.situacao.value}' nao pode se matricular")


# ------------------------------------------------------------ operacoes
def solicitar(db: Session, aluno_id: int, turma_id: int) -> Matricula:
    aluno = obter(db, Aluno, aluno_id, "Aluno")
    turma = obter(db, Turma, turma_id, "Turma", travar=True)
    processar_expiracoes(db, turma)
    disc = turma.disciplina
    regra = REGRAS_CATEGORIA[aluno.categoria]

    _verificar_aluno_ativo(aluno)
    if turma.estado not in TURMA_EM_OFERTA:
        raise Conflito("TURMA_INDISPONIVEL",
                       f"Turma esta '{turma.estado.value}' e nao aceita matriculas")

    duplicada = db.scalars(
        select(Matricula).join(Turma).where(
            Matricula.aluno_id == aluno.id, Matricula.estado.in_(ESTADOS_ATIVOS),
            Turma.disciplina_id == disc.id, Turma.semestre == turma.semestre)
    ).first()
    if duplicada:
        raise Conflito("MATRICULA_DUPLICADA",
                       "Aluno ja possui matricula ativa nesta disciplina no semestre",
                       {"matricula_id": duplicada.id})

    # Regra 3: tres reprovacoes impedem nova matricula
    reprov = _contar_historico(db, aluno.id, disc.id, SH.reprovado)
    if reprov >= MAX_REPROVACOES_DISCIPLINA:
        raise RegraViolada("IMPEDIDO_POR_REPROVACOES",
                           f"Aluno reprovado {reprov} vezes em {disc.codigo}; "
                           "matricula nesta disciplina nao e mais permitida")

    # Regra 1: pre-requisitos aprovados no historico
    reqs = db.scalars(select(PreRequisito).where(PreRequisito.disciplina_id == disc.id)).all()
    faltantes = [p.requisito.codigo for p in reqs
                 if _contar_historico(db, aluno.id, p.requisito_id, SH.aprovado) == 0]
    if faltantes:
        raise RegraViolada("PRE_REQUISITOS_PENDENTES",
                           "Aluno nao foi aprovado em todos os pre-requisitos",
                           {"pendentes": faltantes})

    # Regra 1: limite de creditos (solicitadas, confirmadas e em espera contam)
    atuais = _creditos_no_semestre(db, aluno, turma.semestre)
    if atuais + disc.creditos > regra.max_creditos_semestre:
        raise RegraViolada("LIMITE_CREDITOS_EXCEDIDO",
                           f"Limite de {regra.max_creditos_semestre} creditos/semestre "
                           f"para categoria '{aluno.categoria.value}' seria excedido",
                           {"creditos_atuais": atuais, "creditos_disciplina": disc.creditos,
                            "maximo": regra.max_creditos_semestre})

    # Regra 6: conflito de horario com turma confirmada
    _verificar_conflito_horario(db, aluno, turma)

    # Regra 2: turma lotada -> lista de espera
    lotada = vagas_ocupadas(db, turma) >= turma.vagas
    m = Matricula(aluno=aluno, turma=turma, data=clock.agora(),
                  estado=EM.lista_de_espera if lotada else EM.solicitada)
    db.add(m)
    atualizar_estado_turma(db, turma)
    db.commit()
    return m


def confirmar(db: Session, matricula_id: int) -> Matricula:
    m = obter(db, Matricula, matricula_id, "Matricula")
    turma = obter(db, Turma, m.turma_id, "Turma", travar=True)
    processar_expiracoes(db, turma)
    db.commit()  # persiste expiracoes mesmo que a confirmacao seja recusada

    if m.estado == EM.cancelada and m.motivo_encerramento == MOTIVO_EXPIRACAO:
        raise Conflito("PRAZO_CONFIRMACAO_EXPIRADO",
                       "O prazo de 48h para confirmar a vaga expirou; matricula cancelada")
    if m.estado == EM.lista_de_espera and m.prazo_confirmacao is None:
        raise Conflito("AGUARDANDO_VAGA",
                       "Matricula esta na lista de espera e ainda nao recebeu vaga",
                       {"posicao": posicao_na_fila(db, m)})
    if m.estado not in (EM.solicitada, EM.lista_de_espera):
        raise Conflito("ESTADO_INVALIDO",
                       f"Matricula '{m.estado.value}' nao pode ser confirmada")
    if turma.estado not in TURMA_EM_OFERTA:
        raise Conflito("TURMA_INDISPONIVEL", f"Turma esta '{turma.estado.value}'")

    _verificar_aluno_ativo(m.aluno)
    _verificar_conflito_horario(db, m.aluno, turma)

    m.estado = EM.confirmada
    m.data_confirmacao = clock.agora()
    m.prazo_confirmacao = None
    atualizar_estado_turma(db, turma)
    db.commit()
    return m


def cancelar(db: Session, matricula_id: int) -> tuple[Matricula, bool, bool]:
    m = obter(db, Matricula, matricula_id, "Matricula")
    turma = obter(db, Turma, m.turma_id, "Turma", travar=True)
    processar_expiracoes(db, turma)
    if m.estado not in ESTADOS_ATIVOS:
        db.commit()
        raise Conflito("ESTADO_INVALIDO",
                       f"Matricula '{m.estado.value}' nao pode ser cancelada")

    agora = clock.agora()
    dentro_prazo = True
    reprovacao = False
    if m.estado == EM.confirmada:
        dentro_prazo = agora <= prazo_cancelamento(m)
        if not dentro_prazo:
            # Regra 4: cancelamento fora do prazo -> reprovacao por falta
            db.add(Historico(aluno_id=m.aluno_id, disciplina_id=turma.disciplina_id,
                             semestre=turma.semestre, nota=0.0, situacao=SH.reprovado,
                             observacao="Reprovado por falta (cancelamento fora do prazo)",
                             matricula_id=m.id))
            reprovacao = True

    _encerrar(m, EM.cancelada,
              "cancelada pelo aluno" + ("" if dentro_prazo else " fora do prazo"), agora)
    liberar_vagas(db, turma)
    db.commit()
    return m, dentro_prazo, reprovacao


def trancar(db: Session, matricula_id: int) -> dict:
    m = obter(db, Matricula, matricula_id, "Matricula")
    turma = obter(db, Turma, m.turma_id, "Turma", travar=True)
    aluno = m.aluno
    regra = REGRAS_CATEGORIA[aluno.categoria]

    if m.estado != EM.confirmada:
        raise Conflito("ESTADO_INVALIDO", "Somente matricula confirmada pode ser trancada "
                                          f"(atual: '{m.estado.value}')")
    if regra.max_trancamentos_por_disciplina == 0:
        raise RegraViolada("TRANCAMENTO_NAO_PERMITIDO",
                           f"Categoria '{aluno.categoria.value}' nao permite trancamento")
    agora = clock.agora()
    limite = prazo_cancelamento(m)
    if agora > limite:
        raise RegraViolada("PRAZO_TRANCAMENTO_EXPIRADO",
                           f"Prazo de {regra.prazo_cancelamento_dias} dias para trancamento "
                           "expirado; o cancelamento agora registra reprovacao por falta",
                           {"prazo": limite.isoformat()})
    feitos = _contar_historico(db, aluno.id, turma.disciplina_id, SH.trancado)
    if feitos >= regra.max_trancamentos_por_disciplina:
        raise RegraViolada("LIMITE_TRANCAMENTOS_EXCEDIDO",
                           f"Limite de {regra.max_trancamentos_por_disciplina} trancamento(s) "
                           "nesta disciplina ja atingido", {"trancamentos": feitos})

    _encerrar(m, EM.trancada, "trancada pelo aluno", agora)
    db.add(Historico(aluno_id=aluno.id, disciplina_id=turma.disciplina_id,
                     semestre=turma.semestre, nota=None, situacao=SH.trancado,
                     observacao="Trancamento de disciplina", matricula_id=m.id))
    liberar_vagas(db, turma)

    # Regra 7: terceiro trancamento no semestre tranca o aluno
    db.flush()
    no_semestre = db.scalar(
        select(func.count(Matricula.id)).join(Turma).where(
            Matricula.aluno_id == aluno.id, Matricula.estado == EM.trancada,
            Turma.semestre == turma.semestre)
    ) or 0
    canceladas: list[int] = []
    if no_semestre >= MAX_TRANCAMENTOS_SEMESTRE:
        aluno.situacao = SituacaoAluno.trancado
        for outra in db.scalars(select(Matricula).where(
                Matricula.aluno_id == aluno.id, Matricula.estado == EM.confirmada)).all():
            _encerrar(outra, EM.cancelada,
                      f"aluno atingiu {MAX_TRANCAMENTOS_SEMESTRE} trancamentos no semestre",
                      agora)
            canceladas.append(outra.id)
            liberar_vagas(db, outra.turma)
    db.commit()
    return {"matricula": m, "trancamentos_no_semestre": no_semestre,
            "aluno_trancado": aluno.situacao == SituacaoAluno.trancado,
            "matriculas_canceladas": canceladas}


def cancelar_turma(db: Session, turma: Turma, motivo: str) -> int:
    turma.estado = ET.cancelada
    n = 0
    for m in turma.matriculas:
        if m.estado != EM.cancelada:
            _encerrar(m, EM.cancelada, motivo)
            n += 1
    return n


def encerrar_periodo_matricula(db: Session, semestre: str) -> dict:
    """Regra 5: turma com menos de 5 confirmadas e cancelada com todas as matriculas."""
    turmas = db.scalars(select(Turma).where(Turma.semestre == semestre,
                                            Turma.estado.in_(TURMA_EM_OFERTA))).all()
    canceladas, mantidas = [], []
    for t in turmas:
        processar_expiracoes(db, t)
        conf = sum(1 for m in t.matriculas if m.estado == EM.confirmada)
        if conf < MIN_CONFIRMADAS_TURMA:
            n = cancelar_turma(db, t, f"turma cancelada: menos de {MIN_CONFIRMADAS_TURMA} "
                                      "matriculas confirmadas ao fim do periodo")
            canceladas.append({"turma_id": t.id, "confirmadas": conf,
                               "matriculas_canceladas": n})
        else:
            mantidas.append({"turma_id": t.id, "confirmadas": conf})
    db.commit()
    return {"semestre": semestre, "turmas_canceladas": canceladas,
            "turmas_mantidas": mantidas}
