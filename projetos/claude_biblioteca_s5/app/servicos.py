"""Regras de negocio da biblioteca."""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import clock
from .erros import ErroNegocio, NaoEncontrado
from .models import Emprestimo, Exemplar, Livro, Multa, Reserva, Usuario
from .regras import (
    FATOR_SUSPENSAO, LIMITE_ATRASO_BAIXA_DIAS, LIMITE_ATRASO_SUSPENSAO_DIAS,
    PERDAO_PROFESSOR_MAX_DIAS, PRAZO_RETIRADA_RESERVA_HORAS, regra,
)

EMPRESTIMO_EM_ABERTO = ("ativo", "atrasado")
RESERVA_ATIVA = ("aguardando", "disponivel")
EXEMPLAR_UTILIZAVEL = ("disponivel", "emprestado", "reservado")


def obter(db: Session, modelo, ident: int, nome: str):
    obj = db.get(modelo, ident)
    if obj is None:
        raise NaoEncontrado(nome, ident)
    return obj


def calcular_dias_atraso(emp: Emprestimo, referencia: datetime) -> int:
    """Dias corridos de atraso em relacao a data prevista."""
    return max(0, (referencia.date() - emp.data_prevista).days)


def calcular_multa(categoria: str, dias: int) -> Decimal:
    r = regra(categoria)
    return min(r.multa_por_dia * dias, r.teto_multa).quantize(Decimal("0.01"))


# ---------------------------------------------------------------- Suspensao
def _ha_atraso_grave_em_aberto(db: Session, usuario: Usuario, ref: datetime) -> bool:
    abertos = db.scalars(select(Emprestimo).where(
        Emprestimo.usuario_id == usuario.id, Emprestimo.estado.in_(EMPRESTIMO_EM_ABERTO)))
    return any(calcular_dias_atraso(e, ref) > LIMITE_ATRASO_SUSPENSAO_DIAS for e in abertos)


def _suspender_por_atraso(usuario: Usuario, termino: datetime | None) -> None:
    if usuario.situacao == "suspenso" and usuario.motivo_suspensao == "manual":
        return  # suspensao administrativa prevalece
    usuario.situacao = "suspenso"
    usuario.motivo_suspensao = "atraso"
    if termino is not None and (usuario.suspenso_ate is None or termino > usuario.suspenso_ate):
        usuario.suspenso_ate = termino


# -------------------------------------------------------------------- Filas
def recalcular_fila(db: Session, livro_id: int) -> None:
    db.flush()
    reservas = db.scalars(
        select(Reserva).where(Reserva.livro_id == livro_id)
        .order_by(Reserva.data_reserva, Reserva.id)
    ).all()
    pos = 0
    for r in reservas:
        if r.estado in RESERVA_ATIVA:
            pos += 1
            r.posicao_fila = pos
        else:
            r.posicao_fila = None
    db.flush()


def alocar_exemplar(db: Session, exemplar: Exemplar) -> None:
    """Exemplar acabou de ficar livre: entrega ao primeiro da fila ou deixa disponivel."""
    db.flush()
    proxima = db.scalars(
        select(Reserva).where(Reserva.livro_id == exemplar.livro_id, Reserva.estado == "aguardando")
        .order_by(Reserva.data_reserva, Reserva.id).limit(1)
    ).first()
    if proxima is None:
        exemplar.estado = "disponivel"
    else:
        agora = clock.agora()
        exemplar.estado = "reservado"
        proxima.estado = "disponivel"
        proxima.exemplar_id = exemplar.id
        proxima.data_disponibilizacao = agora
        proxima.expira_em = agora + timedelta(hours=PRAZO_RETIRADA_RESERVA_HORAS)
    recalcular_fila(db, exemplar.livro_id)


def _encerrar_reserva(db: Session, reserva: Reserva, novo_estado: str,
                      liberar_exemplar: bool = True) -> None:
    exemplar = reserva.exemplar if reserva.estado == "disponivel" else None
    reserva.estado = novo_estado
    reserva.posicao_fila = None
    db.flush()
    if liberar_exemplar and exemplar is not None and exemplar.estado == "reservado":
        alocar_exemplar(db, exemplar)
    recalcular_fila(db, reserva.livro_id)


def _cancelar_reservas_se_sem_exemplares(db: Session, livro_id: int) -> None:
    """Regra 6: sem exemplar utilizavel, todas as reservas do livro sao canceladas."""
    db.flush()
    utilizaveis = db.scalar(select(func.count()).select_from(Exemplar).where(
        Exemplar.livro_id == livro_id, Exemplar.estado.in_(EXEMPLAR_UTILIZAVEL)))
    if utilizaveis:
        return
    for r in db.scalars(select(Reserva).where(
            Reserva.livro_id == livro_id, Reserva.estado.in_(RESERVA_ATIVA))):
        r.estado = "cancelada"
        r.posicao_fila = None
        r.exemplar_id = None
        r.expira_em = None
    db.flush()


# ------------------------------------------------------------------ Rotinas
def processar_rotinas(db: Session) -> None:
    """Atualiza estados dependentes do tempo. Executada antes de cada requisicao."""
    agora = clock.agora()

    # Emprestimos em atraso e suspensao automatica (regra 2).
    for emp in db.scalars(select(Emprestimo).where(Emprestimo.estado.in_(EMPRESTIMO_EM_ABERTO))).all():
        dias = calcular_dias_atraso(emp, agora)
        emp.dias_atraso = dias
        if dias > 0 and emp.estado == "ativo":
            emp.estado = "atrasado"
        if dias > LIMITE_ATRASO_SUSPENSAO_DIAS:
            # A duracao (2x os dias) so e conhecida na devolucao; ate la fica suspenso.
            _suspender_por_atraso(emp.usuario, None)
    db.flush()

    # Reservas disponiveis nao retiradas em 48h expiram (regra 4).
    while True:
        vencida = db.scalars(
            select(Reserva).where(Reserva.estado == "disponivel", Reserva.expira_em <= agora)
            .order_by(Reserva.expira_em, Reserva.id).limit(1)
        ).first()
        if vencida is None:
            break
        _encerrar_reserva(db, vencida, "expirada")

    # Fim de suspensoes automaticas.
    for u in db.scalars(select(Usuario).where(
            Usuario.situacao == "suspenso", Usuario.motivo_suspensao == "atraso",
            Usuario.suspenso_ate.is_not(None), Usuario.suspenso_ate <= agora)).all():
        if not _ha_atraso_grave_em_aberto(db, u, agora):
            u.situacao = "ativo"
            u.suspenso_ate = None
            u.motivo_suspensao = None
    db.flush()


# --------------------------------------------------------------- Emprestimo
def criar_emprestimo(db: Session, usuario_id: int, exemplar_id: int) -> Emprestimo:
    usuario = obter(db, Usuario, usuario_id, "Usuario")
    exemplar = obter(db, Exemplar, exemplar_id, "Exemplar")
    r = regra(usuario.categoria)

    # Regra 1
    if usuario.situacao != "ativo":
        raise ErroNegocio("Usuario suspenso nao pode realizar emprestimos", 409, "usuario_suspenso")
    multas_abertas = db.scalar(select(func.count()).select_from(Multa).join(Emprestimo).where(
        Emprestimo.usuario_id == usuario.id, Multa.estado == "aberta"))
    if multas_abertas:
        raise ErroNegocio("Usuario possui multa em aberto", 409, "multa_aberta")
    em_aberto = db.scalar(select(func.count()).select_from(Emprestimo).where(
        Emprestimo.usuario_id == usuario.id, Emprestimo.estado.in_(EMPRESTIMO_EM_ABERTO)))
    if em_aberto >= r.limite_exemplares:
        raise ErroNegocio(
            f"Limite de {r.limite_exemplares} exemplar(es) da categoria {usuario.categoria} atingido",
            409, "limite_exemplares")

    # Estado do exemplar (regra 6 e reservas)
    reserva_usuario = db.scalars(select(Reserva).where(
        Reserva.livro_id == exemplar.livro_id, Reserva.usuario_id == usuario.id,
        Reserva.estado.in_(RESERVA_ATIVA))).first()
    if exemplar.estado == "reservado":
        if not (reserva_usuario and reserva_usuario.estado == "disponivel"
                and reserva_usuario.exemplar_id == exemplar.id):
            raise ErroNegocio("Exemplar reservado para outro usuario", 409, "exemplar_reservado")
    elif exemplar.estado != "disponivel":
        raise ErroNegocio(f"Exemplar indisponivel para emprestimo (estado: {exemplar.estado})",
                          409, "exemplar_indisponivel")

    agora = clock.agora()
    emp = Emprestimo(
        exemplar=exemplar, usuario=usuario, data_retirada=agora,
        data_prevista=agora.date() + timedelta(days=r.prazo_dias),
        estado="ativo", numero_renovacoes=0, dias_atraso=0,
    )
    db.add(emp)
    exemplar.estado = "emprestado"
    if reserva_usuario is not None:
        # Se a reserva do usuario segurava outro exemplar, ele volta para a fila.
        _encerrar_reserva(db, reserva_usuario, "atendida",
                          liberar_exemplar=reserva_usuario.exemplar_id != exemplar.id)
    db.flush()
    return emp


def renovar_emprestimo(db: Session, emprestimo_id: int) -> Emprestimo:
    emp = obter(db, Emprestimo, emprestimo_id, "Emprestimo")
    if emp.estado == "devolvido":
        raise ErroNegocio("Emprestimo ja devolvido", 409, "emprestimo_encerrado")
    agora = clock.agora()
    # Regra 3
    if emp.estado == "atrasado" or calcular_dias_atraso(emp, agora) > 0:
        raise ErroNegocio("Emprestimo atrasado nao pode ser renovado", 409, "emprestimo_atrasado")
    r = regra(emp.usuario.categoria)
    if emp.numero_renovacoes >= r.max_renovacoes:
        raise ErroNegocio(
            f"Limite de {r.max_renovacoes} renovacao(oes) da categoria {emp.usuario.categoria} atingido",
            409, "limite_renovacoes")
    fila = db.scalar(select(func.count()).select_from(Reserva).where(
        Reserva.livro_id == emp.exemplar.livro_id, Reserva.estado.in_(RESERVA_ATIVA)))
    if fila:
        raise ErroNegocio("Ha fila de reserva para este livro", 409, "fila_reserva")

    emp.numero_renovacoes += 1
    emp.data_prevista = agora.date() + timedelta(days=r.prazo_dias)
    db.flush()
    return emp


def devolver_emprestimo(db: Session, emprestimo_id: int) -> Emprestimo:
    emp = obter(db, Emprestimo, emprestimo_id, "Emprestimo")
    if emp.estado == "devolvido":
        raise ErroNegocio("Emprestimo ja devolvido", 409, "emprestimo_encerrado")
    agora = clock.agora()
    usuario, exemplar = emp.usuario, emp.exemplar
    r = regra(usuario.categoria)
    dias = calcular_dias_atraso(emp, agora)

    emp.data_devolucao = agora
    emp.estado = "devolvido"
    emp.dias_atraso = dias

    # Regras 5 e 7: multa
    if dias > 0:
        if dias > LIMITE_ATRASO_BAIXA_DIAS:
            valor, estado = r.teto_multa, "aberta"
        else:
            valor = calcular_multa(usuario.categoria, dias)
            perdoa = usuario.categoria == "professor" and dias <= PERDAO_PROFESSOR_MAX_DIAS
            estado = "perdoada" if perdoa else "aberta"
        db.add(Multa(emprestimo=emp, valor=valor, estado=estado,
                     dias_atraso=dias, data_geracao=agora))

    # Regra 2: suspensao pelo dobro dos dias de atraso, contada da devolucao
    if dias > LIMITE_ATRASO_SUSPENSAO_DIAS:
        _suspender_por_atraso(usuario, agora + timedelta(days=FATOR_SUSPENSAO * dias))

    # Destino do exemplar (regra 7 / regra 4)
    if dias > LIMITE_ATRASO_BAIXA_DIAS:
        exemplar.estado = "baixado"
        _cancelar_reservas_se_sem_exemplares(db, exemplar.livro_id)
    else:
        alocar_exemplar(db, exemplar)
    db.flush()
    return emp


# ------------------------------------------------------------------ Reserva
def criar_reserva(db: Session, usuario_id: int, livro_id: int) -> Reserva:
    usuario = obter(db, Usuario, usuario_id, "Usuario")
    obter(db, Livro, livro_id, "Livro")
    if usuario.situacao != "ativo":
        raise ErroNegocio("Usuario suspenso nao pode reservar", 409, "usuario_suspenso")

    estados = list(db.scalars(select(Exemplar.estado).where(Exemplar.livro_id == livro_id)))
    if not any(e in EXEMPLAR_UTILIZAVEL for e in estados):
        raise ErroNegocio("Livro sem exemplares que possam ser reservados (em reparo/baixados)",
                          409, "sem_exemplar_reservavel")
    if "disponivel" in estados:
        raise ErroNegocio("Ha exemplar disponivel; realize o emprestimo diretamente",
                          409, "exemplar_disponivel")
    duplicada = db.scalar(select(func.count()).select_from(Reserva).where(
        Reserva.livro_id == livro_id, Reserva.usuario_id == usuario_id,
        Reserva.estado.in_(RESERVA_ATIVA)))
    if duplicada:
        raise ErroNegocio("Usuario ja possui reserva ativa para este livro", 409, "reserva_duplicada")
    com_livro = db.scalar(select(func.count()).select_from(Emprestimo).join(Exemplar).where(
        Exemplar.livro_id == livro_id, Emprestimo.usuario_id == usuario_id,
        Emprestimo.estado.in_(EMPRESTIMO_EM_ABERTO)))
    if com_livro:
        raise ErroNegocio("Usuario ja esta com um exemplar deste livro", 409, "livro_ja_emprestado")

    reserva = Reserva(livro_id=livro_id, usuario_id=usuario_id,
                      data_reserva=clock.agora(), estado="aguardando")
    db.add(reserva)
    recalcular_fila(db, livro_id)
    return reserva


def cancelar_reserva(db: Session, reserva_id: int) -> Reserva:
    reserva = obter(db, Reserva, reserva_id, "Reserva")
    if reserva.estado not in RESERVA_ATIVA:
        raise ErroNegocio(f"Reserva nao pode ser cancelada (estado: {reserva.estado})",
                          409, "reserva_encerrada")
    _encerrar_reserva(db, reserva, "cancelada")
    return reserva


# ----------------------------------------------------------------- Exemplar
def alterar_estado_exemplar(db: Session, exemplar: Exemplar, novo: str) -> None:
    atual = exemplar.estado
    if novo == atual:
        return
    if atual == "emprestado":
        raise ErroNegocio("Exemplar emprestado: registre a devolucao antes de alterar o estado",
                          409, "exemplar_emprestado")
    if atual == "baixado":
        raise ErroNegocio("Exemplar baixado nao pode voltar ao acervo", 409, "exemplar_baixado")

    if atual == "reservado":
        # A reserva que aguardava este exemplar volta para a fila, mantendo a posicao.
        for r in db.scalars(select(Reserva).where(
                Reserva.exemplar_id == exemplar.id, Reserva.estado == "disponivel")).all():
            r.estado = "aguardando"
            r.exemplar_id = None
            r.data_disponibilizacao = None
            r.expira_em = None

    if novo == "disponivel":
        alocar_exemplar(db, exemplar)
    else:
        exemplar.estado = novo
        if novo == "baixado":
            _cancelar_reservas_se_sem_exemplares(db, exemplar.livro_id)
        recalcular_fila(db, exemplar.livro_id)


# -------------------------------------------------------------------- Multa
def pagar_multa(db: Session, multa_id: int) -> Multa:
    multa = obter(db, Multa, multa_id, "Multa")
    if multa.estado != "aberta":
        raise ErroNegocio(f"Multa nao esta em aberto (estado: {multa.estado})", 409, "multa_nao_aberta")
    multa.estado = "paga"
    multa.data_pagamento = clock.agora()
    db.flush()
    return multa
