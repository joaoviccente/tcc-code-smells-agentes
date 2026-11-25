"""Regras de negocio da biblioteca."""
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.enums import (
    Categoria,
    EstadoEmprestimo,
    EstadoExemplar,
    EstadoMulta,
    EstadoReserva,
    SituacaoUsuario,
)
from app.erros import ErroNegocio, NaoEncontrado
from app.models import Emprestimo, Exemplar, Livro, Multa, Reserva, Usuario
from app.regras import (
    DIAS_ATRASO_PARA_BAIXA,
    DIAS_ATRASO_PARA_SUSPENSAO,
    DIAS_PERDAO_PROFESSOR,
    FATOR_DURACAO_SUSPENSAO,
    HORAS_PARA_RETIRADA_RESERVA,
    REGRAS,
)

EMPRESTIMO_EM_ABERTO = (EstadoEmprestimo.ATIVO, EstadoEmprestimo.ATRASADO)
RESERVA_ATIVA = (EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL)
# Exemplares que ainda podem atender a fila de reservas
EXEMPLAR_CIRCULANTE = (EstadoExemplar.DISPONIVEL, EstadoExemplar.EMPRESTADO, EstadoExemplar.RESERVADO)


def obter(db: Session, modelo, id_: int, nome: str):
    obj = db.get(modelo, id_)
    if obj is None:
        raise NaoEncontrado(nome, id_)
    return obj


# ====================================================================== calculos
def dias_atraso(emp: Emprestimo, referencia: datetime) -> int:
    """Dias corridos de atraso (ate a devolucao, ou ate a referencia se ainda aberto)."""
    fim = emp.data_devolucao or referencia
    return max(0, (fim.date() - emp.data_prevista.date()).days)


def valor_multa_centavos(categoria: Categoria, dias: int) -> int:
    regra = REGRAS[categoria]
    return min(dias * regra.multa_diaria_centavos, regra.teto_multa_centavos)


# ====================================================================== multa / suspensao
def _registrar_multa(db: Session, emp: Emprestimo, dias: int, final: bool) -> None:
    """Cria/atualiza a multa do emprestimo (regras 5 e 7)."""
    categoria = emp.usuario.categoria
    regra = REGRAS[categoria]
    perdoavel = categoria == Categoria.PROFESSOR and dias <= DIAS_PERDAO_PROFESSOR

    # Enquanto o emprestimo esta aberto, a multa de professor com ate 2 dias
    # ainda sera perdoada se devolvido a tempo: nao e materializada como "aberta".
    if not final and perdoavel:
        return

    multa = emp.multa
    if multa is not None and multa.estado != EstadoMulta.ABERTA:
        return
    if multa is None:
        multa = Multa(emprestimo=emp, valor_centavos=0, dias_atraso=0, estado=EstadoMulta.ABERTA)
        db.add(multa)

    multa.dias_atraso = dias
    if final and dias > DIAS_ATRASO_PARA_BAIXA:
        multa.valor_centavos = regra.teto_multa_centavos  # regra 7
    else:
        multa.valor_centavos = valor_multa_centavos(categoria, dias)  # regra 5
    if final and perdoavel:
        multa.estado = EstadoMulta.PERDOADA


def _suspender(usuario: Usuario, inicio: date, dias: int) -> None:
    """Regra 2: suspensao com duracao igual ao dobro dos dias de atraso."""
    if usuario.situacao == SituacaoUsuario.SUSPENSO and usuario.suspenso_ate is None:
        return  # suspensao manual por tempo indeterminado prevalece
    fim = inicio + timedelta(days=FATOR_DURACAO_SUSPENSAO * dias)
    usuario.situacao = SituacaoUsuario.SUSPENSO
    if usuario.suspenso_ate is None or fim > usuario.suspenso_ate:
        usuario.suspenso_ate = fim


# ====================================================================== fila de reservas
def renumerar_fila(db: Session, livro_id: int) -> None:
    db.flush()
    reservas = db.scalars(
        select(Reserva).where(Reserva.livro_id == livro_id, Reserva.estado.in_(RESERVA_ATIVA))
        .order_by(Reserva.data, Reserva.id)
    ).all()
    pos = 0
    for r in reservas:
        if r.estado == EstadoReserva.AGUARDANDO:
            pos += 1
            r.posicao = pos
        else:
            r.posicao = None
    db.flush()


def liberar_exemplar(db: Session, exemplar: Exemplar, momento: datetime) -> None:
    """Exemplar voltou a circular: atende o primeiro da fila (regra 4) ou fica disponivel."""
    db.flush()
    primeira = db.scalars(
        select(Reserva).where(Reserva.livro_id == exemplar.livro_id, Reserva.estado == EstadoReserva.AGUARDANDO)
        .order_by(Reserva.data, Reserva.id).limit(1)
    ).first()
    if primeira is None:
        exemplar.estado = EstadoExemplar.DISPONIVEL
    else:
        exemplar.estado = EstadoExemplar.RESERVADO
        primeira.estado = EstadoReserva.DISPONIVEL
        primeira.exemplar_id = exemplar.id
        primeira.disponivel_em = momento
        primeira.expira_em = momento + timedelta(hours=HORAS_PARA_RETIRADA_RESERVA)
    renumerar_fila(db, exemplar.livro_id)


def verificar_cancelamento_reservas(db: Session, livro_id: int) -> None:
    """Regra 6: sem exemplar que possa circular, todas as reservas do livro sao canceladas."""
    db.flush()
    circulantes = db.scalar(
        select(func.count()).select_from(Exemplar)
        .where(Exemplar.livro_id == livro_id, Exemplar.estado.in_(EXEMPLAR_CIRCULANTE))
    )
    if circulantes:
        return
    for r in db.scalars(select(Reserva).where(Reserva.livro_id == livro_id, Reserva.estado.in_(RESERVA_ATIVA))):
        r.estado = EstadoReserva.CANCELADA
        r.posicao = None
    db.flush()


# ====================================================================== processamento temporal
def processar_pendencias(db: Session) -> None:
    """Aplica as regras dependentes do tempo. Executado no inicio de cada requisicao."""
    agora = clock.agora()
    hoje = agora.date()

    # Emprestimos em atraso: estado, multa acumulada e suspensao (regras 2 e 5)
    abertos = db.scalars(select(Emprestimo).where(Emprestimo.estado.in_(EMPRESTIMO_EM_ABERTO))).all()
    for emp in abertos:
        dias = dias_atraso(emp, agora)
        if dias <= 0:
            continue
        emp.estado = EstadoEmprestimo.ATRASADO
        _registrar_multa(db, emp, dias, final=False)
        if dias > DIAS_ATRASO_PARA_SUSPENSAO:
            _suspender(emp.usuario, hoje, dias)
    db.flush()

    # Reservas com prazo de retirada esgotado (regra 4), em ordem cronologica,
    # para que a vez passe ao proximo a partir do instante exato da expiracao.
    while True:
        r = db.scalars(
            select(Reserva).where(Reserva.estado == EstadoReserva.DISPONIVEL, Reserva.expira_em <= agora)
            .order_by(Reserva.expira_em, Reserva.id).limit(1)
        ).first()
        if r is None:
            break
        r.estado = EstadoReserva.EXPIRADA
        r.posicao = None
        if r.exemplar is not None and r.exemplar.estado == EstadoExemplar.RESERVADO:
            liberar_exemplar(db, r.exemplar, r.expira_em)
        else:
            renumerar_fila(db, r.livro_id)

    # Fim de suspensoes automaticas
    vencidas = db.scalars(select(Usuario).where(
        Usuario.situacao == SituacaoUsuario.SUSPENSO,
        Usuario.suspenso_ate.is_not(None), Usuario.suspenso_ate <= hoje)).all()
    for u in vencidas:
        u.situacao = SituacaoUsuario.ATIVO
        u.suspenso_ate = None
    db.flush()


# ====================================================================== emprestimos
def contar_emprestimos_abertos(db: Session, usuario_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Emprestimo).where(
        Emprestimo.usuario_id == usuario_id, Emprestimo.estado.in_(EMPRESTIMO_EM_ABERTO)))


def possui_multa_aberta(db: Session, usuario_id: int) -> bool:
    return bool(db.scalar(select(func.count()).select_from(Multa).join(Emprestimo).where(
        Emprestimo.usuario_id == usuario_id, Multa.estado == EstadoMulta.ABERTA)))


def criar_emprestimo(db: Session, usuario_id: int, exemplar_id: int) -> Emprestimo:
    usuario: Usuario = obter(db, Usuario, usuario_id, "Usuario")
    exemplar: Exemplar = obter(db, Exemplar, exemplar_id, "Exemplar")
    regra = REGRAS[usuario.categoria]

    # Regra 1
    if usuario.situacao != SituacaoUsuario.ATIVO:
        raise ErroNegocio("Usuario suspenso nao pode realizar emprestimos")
    if possui_multa_aberta(db, usuario.id):
        raise ErroNegocio("Usuario possui multa em aberto")
    if contar_emprestimos_abertos(db, usuario.id) >= regra.limite_exemplares:
        raise ErroNegocio(f"Limite de {regra.limite_exemplares} exemplar(es) da categoria "
                          f"{usuario.categoria.value} atingido")

    reserva = db.scalars(select(Reserva).where(
        Reserva.usuario_id == usuario.id, Reserva.livro_id == exemplar.livro_id,
        Reserva.estado.in_(RESERVA_ATIVA))).first()

    # Regra 6 e controle de exemplares reservados
    if exemplar.estado == EstadoExemplar.RESERVADO:
        if reserva is None or reserva.exemplar_id != exemplar.id:
            raise ErroNegocio("Exemplar reservado para outro usuario")
    elif exemplar.estado != EstadoExemplar.DISPONIVEL:
        raise ErroNegocio(f"Exemplar no estado '{exemplar.estado.value}' nao pode ser emprestado")

    agora = clock.agora()
    emp = Emprestimo(exemplar=exemplar, usuario=usuario, data_retirada=agora,
                     data_prevista=agora + timedelta(days=regra.prazo_dias),
                     estado=EstadoEmprestimo.ATIVO, renovacoes=0)
    db.add(emp)
    exemplar.estado = EstadoExemplar.EMPRESTADO

    if reserva is not None:
        outro = reserva.exemplar if reserva.exemplar_id not in (None, exemplar.id) else None
        reserva.estado = EstadoReserva.ATENDIDA
        reserva.posicao = None
        if outro is not None and outro.estado == EstadoExemplar.RESERVADO:
            liberar_exemplar(db, outro, agora)
        else:
            renumerar_fila(db, exemplar.livro_id)
    db.flush()
    return emp


def renovar_emprestimo(db: Session, emprestimo_id: int) -> Emprestimo:
    emp: Emprestimo = obter(db, Emprestimo, emprestimo_id, "Emprestimo")
    regra = REGRAS[emp.usuario.categoria]

    if emp.estado == EstadoEmprestimo.DEVOLVIDO:
        raise ErroNegocio("Emprestimo ja devolvido")
    # Regra 3
    if emp.estado == EstadoEmprestimo.ATRASADO:
        raise ErroNegocio("Emprestimo atrasado nao pode ser renovado")
    if emp.renovacoes >= regra.max_renovacoes:
        raise ErroNegocio(f"Limite de {regra.max_renovacoes} renovacao(oes) da categoria "
                          f"{emp.usuario.categoria.value} atingido")
    fila = db.scalar(select(func.count()).select_from(Reserva).where(
        Reserva.livro_id == emp.exemplar.livro_id, Reserva.estado == EstadoReserva.AGUARDANDO))
    if fila:
        raise ErroNegocio("Ha fila de reserva para este livro")

    emp.data_prevista = clock.agora() + timedelta(days=regra.prazo_dias)
    emp.renovacoes += 1
    db.flush()
    return emp


def devolver_emprestimo(db: Session, emprestimo_id: int) -> Emprestimo:
    emp: Emprestimo = obter(db, Emprestimo, emprestimo_id, "Emprestimo")
    if emp.estado == EstadoEmprestimo.DEVOLVIDO:
        raise ErroNegocio("Emprestimo ja devolvido")

    agora = clock.agora()
    emp.data_devolucao = agora
    emp.estado = EstadoEmprestimo.DEVOLVIDO
    dias = dias_atraso(emp, agora)

    if dias > 0:
        _registrar_multa(db, emp, dias, final=True)  # regras 5 e 7
    if dias > DIAS_ATRASO_PARA_SUSPENSAO:
        _suspender(emp.usuario, agora.date(), dias)  # regra 2

    exemplar = emp.exemplar
    if dias > DIAS_ATRASO_PARA_BAIXA:  # regra 7
        exemplar.estado = EstadoExemplar.BAIXADO
        verificar_cancelamento_reservas(db, exemplar.livro_id)  # regra 6
    else:
        liberar_exemplar(db, exemplar, agora)  # regra 4
    db.flush()
    return emp


# ====================================================================== reservas
def criar_reserva(db: Session, usuario_id: int, livro_id: int) -> Reserva:
    usuario: Usuario = obter(db, Usuario, usuario_id, "Usuario")
    livro: Livro = obter(db, Livro, livro_id, "Livro")

    if usuario.situacao != SituacaoUsuario.ATIVO:
        raise ErroNegocio("Usuario suspenso nao pode realizar reservas")

    estados = [e.estado for e in livro.exemplares]
    if not any(e in EXEMPLAR_CIRCULANTE for e in estados):
        # Regra 6: exemplares em reparo ou baixados nao podem ser reservados
        raise ErroNegocio("Livro sem exemplares que possam ser reservados (em reparo, baixados ou inexistentes)")
    if EstadoExemplar.DISPONIVEL in estados:
        raise ErroNegocio("Ha exemplar disponivel deste livro; realize o emprestimo diretamente")

    if db.scalar(select(func.count()).select_from(Reserva).where(
            Reserva.usuario_id == usuario.id, Reserva.livro_id == livro.id, Reserva.estado.in_(RESERVA_ATIVA))):
        raise ErroNegocio("Usuario ja possui reserva ativa para este livro")
    if db.scalar(select(func.count()).select_from(Emprestimo).join(Exemplar).where(
            Emprestimo.usuario_id == usuario.id, Exemplar.livro_id == livro.id,
            Emprestimo.estado.in_(EMPRESTIMO_EM_ABERTO))):
        raise ErroNegocio("Usuario ja esta com um exemplar deste livro emprestado")

    reserva = Reserva(livro=livro, usuario=usuario, data=clock.agora(), estado=EstadoReserva.AGUARDANDO)
    db.add(reserva)
    renumerar_fila(db, livro.id)
    return reserva


def cancelar_reserva(db: Session, reserva_id: int) -> Reserva:
    reserva: Reserva = obter(db, Reserva, reserva_id, "Reserva")
    if reserva.estado not in RESERVA_ATIVA:
        raise ErroNegocio(f"Reserva no estado '{reserva.estado.value}' nao pode ser cancelada")
    estava_disponivel = reserva.estado == EstadoReserva.DISPONIVEL
    reserva.estado = EstadoReserva.CANCELADA
    reserva.posicao = None
    if estava_disponivel and reserva.exemplar is not None and reserva.exemplar.estado == EstadoExemplar.RESERVADO:
        liberar_exemplar(db, reserva.exemplar, clock.agora())
    else:
        renumerar_fila(db, reserva.livro_id)
    return reserva


def fila_do_livro(db: Session, livro_id: int) -> list[Reserva]:
    obter(db, Livro, livro_id, "Livro")
    reservas = db.scalars(select(Reserva).where(Reserva.livro_id == livro_id, Reserva.estado.in_(RESERVA_ATIVA))
                          .order_by(Reserva.data, Reserva.id)).all()
    # Reservas ja disponiveis (aguardando retirada) aparecem primeiro
    return sorted(reservas, key=lambda r: (r.estado != EstadoReserva.DISPONIVEL, r.data, r.id))


# ====================================================================== multas
def pagar_multa(db: Session, multa_id: int) -> Multa:
    multa: Multa = obter(db, Multa, multa_id, "Multa")
    if multa.estado != EstadoMulta.ABERTA:
        raise ErroNegocio(f"Multa no estado '{multa.estado.value}' nao pode ser paga")
    if multa.emprestimo.estado != EstadoEmprestimo.DEVOLVIDO:
        raise ErroNegocio("Multa ainda em apuracao: o exemplar precisa ser devolvido antes do pagamento")
    multa.estado = EstadoMulta.PAGA
    multa.data_pagamento = clock.agora()
    db.flush()
    return multa


# ====================================================================== exemplares
TRANSICOES_MANUAIS = {
    EstadoExemplar.DISPONIVEL: {EstadoExemplar.EM_REPARO, EstadoExemplar.BAIXADO},
    EstadoExemplar.EM_REPARO: {EstadoExemplar.DISPONIVEL, EstadoExemplar.BAIXADO},
}


def alterar_estado_exemplar(db: Session, exemplar: Exemplar, novo: EstadoExemplar) -> None:
    atual = exemplar.estado
    if novo == atual:
        return
    if novo not in TRANSICOES_MANUAIS.get(atual, set()):
        raise ErroNegocio(f"Transicao de estado '{atual.value}' -> '{novo.value}' nao permitida manualmente")
    if novo == EstadoExemplar.DISPONIVEL:
        liberar_exemplar(db, exemplar, clock.agora())
    else:
        exemplar.estado = novo
        if novo == EstadoExemplar.BAIXADO:
            verificar_cancelamento_reservas(db, exemplar.livro_id)  # regra 6
