"""Regras de negocio da biblioteca.

Os eventos que dependem da passagem do tempo (atraso de emprestimos, acumulo de
multas, suspensao automatica, fim de suspensao e expiracao de reservas) sao
processados de forma "preguicosa" por `processar_pendencias`, executada no inicio
de cada requisicao. Assim o estado lido pela API esta sempre atualizado sem
depender de um agendador externo.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import relogio
from .enums import (
    ESTADOS_EMPRESTIMO_EM_ABERTO,
    ESTADOS_EXEMPLAR_EM_CIRCULACAO,
    ESTADOS_RESERVA_NA_FILA,
    Categoria,
    EstadoEmprestimo,
    EstadoExemplar,
    EstadoMulta,
    EstadoReserva,
    SituacaoUsuario,
)
from .models import Emprestimo, Exemplar, Livro, Multa, Reserva, Usuario
from .regras import (
    DIAS_ATRASO_PARA_BAIXA,
    DIAS_ATRASO_PARA_SUSPENSAO,
    DIAS_PERDAO_PROFESSOR,
    FATOR_DIAS_SUSPENSAO,
    HORAS_PARA_RETIRADA_RESERVA,
    regra,
)


class ErroNegocio(Exception):
    """Violacao de regra de negocio -> HTTP 409 (ou outro status informado)."""

    def __init__(self, mensagem: str, status_code: int = 409):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status_code = status_code


class NaoEncontrado(ErroNegocio):
    def __init__(self, recurso: str, ident: int):
        super().__init__(f"{recurso} {ident} nao encontrado", 404)


def obter(db: Session, modelo, ident: int, nome: str):
    obj = db.get(modelo, ident)
    if obj is None:
        raise NaoEncontrado(nome, ident)
    return obj


# =========================================================================== multas
def calcular_multa(categoria: Categoria, dias: int, na_devolucao: bool) -> tuple[int, EstadoMulta] | None:
    """Retorna (valor_em_centavos, estado) para `dias` de atraso, ou None se nao ha atraso."""
    if dias <= 0:
        return None
    r = regra(categoria)
    if na_devolucao and dias > DIAS_ATRASO_PARA_BAIXA:
        # Regra 7: multa no valor do teto da categoria.
        return r.teto_multa_centavos, EstadoMulta.aberta
    valor = min(dias * r.multa_diaria_centavos, r.teto_multa_centavos)  # Regra 5
    if categoria == Categoria.professor and dias <= DIAS_PERDAO_PROFESSOR:
        return valor, EstadoMulta.perdoada
    return valor, EstadoMulta.aberta


def sincronizar_multa(db: Session, emp: Emprestimo, agora: datetime, na_devolucao: bool) -> Multa | None:
    dias = emp.dias_atraso
    calculo = calcular_multa(emp.categoria_usuario, dias, na_devolucao)
    multa = emp.multa
    if calculo is None or (multa is not None and multa.estado == EstadoMulta.paga):
        return multa
    valor, estado = calculo
    if multa is None:
        multa = Multa(emprestimo=emp, data_geracao=agora, valor_centavos=valor, dias_atraso=dias, estado=estado)
        db.add(multa)
    multa.valor_centavos = valor
    multa.dias_atraso = dias
    multa.estado = estado
    return multa


def usuario_tem_multa_aberta(db: Session, usuario_id: int) -> bool:
    q = (select(func.count(Multa.id)).join(Emprestimo)
         .where(Emprestimo.usuario_id == usuario_id, Multa.estado == EstadoMulta.aberta))
    return db.scalar(q) > 0


def pagar_multa(db: Session, multa: Multa, valor_informado: Decimal | None) -> Multa:
    if multa.estado != EstadoMulta.aberta:
        raise ErroNegocio(f"multa nao esta aberta (estado atual: {multa.estado})")
    if not multa.valor_definitivo:
        raise ErroNegocio("multa ainda esta acumulando; o pagamento so e possivel apos a devolucao do exemplar")
    if valor_informado is not None and valor_informado.quantize(Decimal("0.01")) != multa.valor:
        raise ErroNegocio(f"valor informado ({valor_informado}) difere do valor da multa ({multa.valor})", 422)
    multa.estado = EstadoMulta.paga
    multa.data_pagamento = relogio.agora()
    return multa


# =========================================================================== suspensao
def aplicar_suspensao(emp: Emprestimo, agora: datetime) -> None:
    """Regra 2: atraso > 15 dias suspende o usuario por 2x os dias de atraso.

    A contagem da suspensao parte da devolucao; enquanto o exemplar nao e
    devolvido, o fim da suspensao e recalculado diariamente (o atraso cresce).
    """
    dias = emp.dias_atraso
    if dias <= DIAS_ATRASO_PARA_SUSPENSAO:
        return
    usuario = emp.usuario
    if usuario.situacao == SituacaoUsuario.suspenso and usuario.suspensao_ate is None:
        return  # suspensao manual por tempo indeterminado prevalece
    base = (emp.data_devolucao or agora).date()
    fim = base + timedelta(days=FATOR_DIAS_SUSPENSAO * dias)
    usuario.situacao = SituacaoUsuario.suspenso
    if usuario.suspensao_ate is None or fim > usuario.suspensao_ate:
        usuario.suspensao_ate = fim


# =========================================================================== reservas / fila
def fila_do_livro(db: Session, livro_id: int) -> list[Reserva]:
    q = (select(Reserva)
         .where(Reserva.livro_id == livro_id, Reserva.estado.in_(ESTADOS_RESERVA_NA_FILA))
         .order_by(Reserva.data_reserva, Reserva.id))
    return list(db.scalars(q))


def recalcular_fila(db: Session, livro_id: int) -> None:
    db.flush()
    for pos, r in enumerate(fila_do_livro(db, livro_id), start=1):
        r.posicao = pos


def _encerrar_reserva(r: Reserva, estado: EstadoReserva, quando: datetime) -> None:
    r.estado = estado
    r.posicao = None
    r.encerrada_em = quando


def alocar_exemplar(db: Session, exemplar: Exemplar, inicio: datetime) -> None:
    """Exemplar voltou a circular: entrega ao primeiro da fila (Regra 4) ou fica disponivel."""
    proxima = db.scalars(
        select(Reserva)
        .where(Reserva.livro_id == exemplar.livro_id, Reserva.estado == EstadoReserva.aguardando)
        .order_by(Reserva.data_reserva, Reserva.id).limit(1)
    ).first()
    if proxima is None:
        exemplar.estado = EstadoExemplar.disponivel
    else:
        exemplar.estado = EstadoExemplar.reservado
        proxima.estado = EstadoReserva.disponivel
        proxima.exemplar = exemplar
        proxima.disponivel_em = inicio
        proxima.expira_em = inicio + timedelta(hours=HORAS_PARA_RETIRADA_RESERVA)
    recalcular_fila(db, exemplar.livro_id)


def _reserva_que_segura(db: Session, exemplar: Exemplar) -> Reserva | None:
    return db.scalars(select(Reserva).where(
        Reserva.exemplar_id == exemplar.id, Reserva.estado == EstadoReserva.disponivel)).first()


def _devolver_reserva_a_fila(db: Session, exemplar: Exemplar, agora: datetime) -> None:
    """O exemplar separado para uma reserva deixou de estar disponivel (reparo/baixa):
    a reserva volta a aguardar (mantendo a ordem de chegada) e, se houver outro
    exemplar disponivel do mesmo livro, ele e alocado a fila."""
    reserva = _reserva_que_segura(db, exemplar)
    if reserva is None:
        return
    reserva.estado = EstadoReserva.aguardando
    reserva.exemplar = None
    reserva.disponivel_em = None
    reserva.expira_em = None
    db.flush()
    outro = db.scalars(select(Exemplar).where(
        Exemplar.livro_id == exemplar.livro_id,
        Exemplar.estado == EstadoExemplar.disponivel,
        Exemplar.id != exemplar.id)).first()
    if outro is not None:
        alocar_exemplar(db, outro, agora)
    else:
        recalcular_fila(db, exemplar.livro_id)


def cancelar_reservas_se_sem_acervo(db: Session, livro_id: int, agora: datetime) -> None:
    """Regra 6: baixado o ultimo exemplar em circulacao, todas as reservas sao canceladas."""
    em_circulacao = db.scalar(select(func.count(Exemplar.id)).where(
        Exemplar.livro_id == livro_id, Exemplar.estado.in_(ESTADOS_EXEMPLAR_EM_CIRCULACAO)))
    if em_circulacao:
        return
    for r in fila_do_livro(db, livro_id):
        _encerrar_reserva(r, EstadoReserva.cancelada, agora)


def criar_reserva(db: Session, usuario_id: int, livro_id: int) -> Reserva:
    agora = relogio.agora()
    usuario = obter(db, Usuario, usuario_id, "usuario")
    livro = obter(db, Livro, livro_id, "livro")
    if usuario.situacao != SituacaoUsuario.ativo:
        raise ErroNegocio("usuario suspenso nao pode reservar")

    estados = [e.estado for e in livro.exemplares]
    if not any(e in ESTADOS_EXEMPLAR_EM_CIRCULACAO for e in estados):
        raise ErroNegocio("livro nao possui exemplares em circulacao (em reparo ou baixados nao podem ser reservados)")
    if EstadoExemplar.disponivel in estados:
        raise ErroNegocio("ha exemplar disponivel deste livro; realize o emprestimo diretamente")
    if any(r.usuario_id == usuario_id for r in fila_do_livro(db, livro_id)):
        raise ErroNegocio("usuario ja possui reserva ativa para este livro")
    ja_com_livro = db.scalar(select(func.count(Emprestimo.id)).join(Exemplar).where(
        Emprestimo.usuario_id == usuario_id, Exemplar.livro_id == livro_id,
        Emprestimo.estado.in_(ESTADOS_EMPRESTIMO_EM_ABERTO)))
    if ja_com_livro:
        raise ErroNegocio("usuario ja esta com um exemplar deste livro emprestado")

    reserva = Reserva(livro=livro, usuario=usuario, data_reserva=agora, estado=EstadoReserva.aguardando)
    db.add(reserva)
    recalcular_fila(db, livro_id)
    return reserva


def cancelar_reserva(db: Session, reserva: Reserva) -> Reserva:
    if reserva.estado not in ESTADOS_RESERVA_NA_FILA:
        raise ErroNegocio(f"reserva nao pode ser cancelada (estado atual: {reserva.estado})")
    agora = relogio.agora()
    exemplar = reserva.exemplar if reserva.estado == EstadoReserva.disponivel else None
    _encerrar_reserva(reserva, EstadoReserva.cancelada, agora)
    if exemplar is not None:
        alocar_exemplar(db, exemplar, agora)  # passa a vez ao proximo
    else:
        recalcular_fila(db, reserva.livro_id)
    return reserva


# =========================================================================== emprestimos
def _emprestimos_em_aberto(db: Session, usuario_id: int) -> int:
    return db.scalar(select(func.count(Emprestimo.id)).where(
        Emprestimo.usuario_id == usuario_id, Emprestimo.estado.in_(ESTADOS_EMPRESTIMO_EM_ABERTO)))


def criar_emprestimo(db: Session, usuario_id: int, exemplar_id: int) -> Emprestimo:
    agora = relogio.agora()
    usuario = obter(db, Usuario, usuario_id, "usuario")
    exemplar = obter(db, Exemplar, exemplar_id, "exemplar")
    r = regra(usuario.categoria)

    # Regra 1
    if usuario.situacao != SituacaoUsuario.ativo:
        raise ErroNegocio("usuario suspenso nao pode realizar emprestimos")
    if usuario_tem_multa_aberta(db, usuario.id):
        raise ErroNegocio("usuario possui multa em aberto")
    if _emprestimos_em_aberto(db, usuario.id) >= r.limite_exemplares:
        raise ErroNegocio(f"limite de {r.limite_exemplares} exemplar(es) da categoria {usuario.categoria} atingido")

    # Regra 6 e disponibilidade do exemplar
    if exemplar.estado in (EstadoExemplar.em_reparo, EstadoExemplar.baixado):
        raise ErroNegocio(f"exemplar {exemplar.estado} nao pode ser emprestado")
    if exemplar.estado == EstadoExemplar.emprestado:
        raise ErroNegocio("exemplar ja esta emprestado")

    reserva_do_usuario = db.scalars(select(Reserva).where(
        Reserva.livro_id == exemplar.livro_id, Reserva.usuario_id == usuario.id,
        Reserva.estado == EstadoReserva.disponivel)).first()

    if exemplar.estado == EstadoExemplar.reservado:
        if reserva_do_usuario is None or reserva_do_usuario.exemplar_id != exemplar.id:
            raise ErroNegocio("exemplar esta reservado para outro usuario")

    if reserva_do_usuario is not None:
        _encerrar_reserva(reserva_do_usuario, EstadoReserva.atendida, agora)
        separado = reserva_do_usuario.exemplar
        if separado is not None and separado.id != exemplar.id:
            alocar_exemplar(db, separado, agora)  # libera o exemplar que estava separado

    emp = Emprestimo(
        exemplar=exemplar, usuario=usuario, categoria_usuario=usuario.categoria,
        data_retirada=agora, data_prevista=agora.date() + timedelta(days=r.prazo_dias),
        estado=EstadoEmprestimo.ativo, renovacoes=0,
    )
    exemplar.estado = EstadoExemplar.emprestado
    db.add(emp)
    recalcular_fila(db, exemplar.livro_id)
    return emp


def renovar_emprestimo(db: Session, emp: Emprestimo) -> Emprestimo:
    agora = relogio.agora()
    if emp.estado == EstadoEmprestimo.devolvido:
        raise ErroNegocio("emprestimo ja devolvido")
    # Regra 3
    if emp.estado == EstadoEmprestimo.atrasado or emp.dias_atraso > 0:
        raise ErroNegocio("emprestimo atrasado nao pode ser renovado")
    if fila_do_livro(db, emp.livro_id):
        raise ErroNegocio("ha fila de reserva para este livro")
    r = regra(emp.categoria_usuario)
    if emp.renovacoes >= r.max_renovacoes:
        raise ErroNegocio(f"limite de {r.max_renovacoes} renovacao(oes) da categoria {emp.categoria_usuario} atingido")
    emp.renovacoes += 1
    emp.data_prevista = agora.date() + timedelta(days=r.prazo_dias)
    return emp


def devolver_emprestimo(db: Session, emp: Emprestimo) -> Emprestimo:
    if emp.estado == EstadoEmprestimo.devolvido:
        raise ErroNegocio("emprestimo ja devolvido")
    agora = relogio.agora()
    emp.data_devolucao = agora
    emp.estado = EstadoEmprestimo.devolvido
    dias = emp.dias_atraso

    sincronizar_multa(db, emp, agora, na_devolucao=True)  # Regras 5 e 7
    aplicar_suspensao(emp, agora)                         # Regra 2

    exemplar = emp.exemplar
    if dias > DIAS_ATRASO_PARA_BAIXA:                     # Regra 7
        exemplar.estado = EstadoExemplar.baixado
        db.flush()
        cancelar_reservas_se_sem_acervo(db, exemplar.livro_id, agora)  # Regra 6
    else:
        alocar_exemplar(db, exemplar, agora)              # Regra 4
    return emp


# =========================================================================== exemplares
def alterar_estado_exemplar(db: Session, exemplar: Exemplar, novo: EstadoExemplar) -> None:
    atual = exemplar.estado
    if novo == atual:
        return
    if atual == EstadoExemplar.baixado:
        raise ErroNegocio("exemplar baixado nao pode mudar de estado")
    if atual == EstadoExemplar.emprestado:
        raise ErroNegocio("exemplar emprestado; registre a devolucao antes de alterar o estado")
    agora = relogio.agora()

    if atual == EstadoExemplar.reservado:
        exemplar.estado = novo
        _devolver_reserva_a_fila(db, exemplar, agora)
    elif novo == EstadoExemplar.disponivel:
        alocar_exemplar(db, exemplar, agora)  # saiu do reparo: atende a fila, se houver
    else:
        exemplar.estado = novo

    if novo == EstadoExemplar.baixado:
        db.flush()
        cancelar_reservas_se_sem_acervo(db, exemplar.livro_id, agora)


# =========================================================================== processamento temporal
def processar_pendencias(db: Session) -> None:
    agora = relogio.agora()

    # Regra 4: reservas disponiveis nao retiradas em 48h expiram e a vez passa ao proximo.
    # O prazo do proximo comeca quando o anterior expirou (processamento em cadeia).
    while True:
        vencidas = list(db.scalars(select(Reserva).where(
            Reserva.estado == EstadoReserva.disponivel, Reserva.expira_em < agora
        ).order_by(Reserva.expira_em)))
        if not vencidas:
            break
        for r in vencidas:
            _encerrar_reserva(r, EstadoReserva.expirada, r.expira_em)
            if r.exemplar is not None:
                alocar_exemplar(db, r.exemplar, r.expira_em)
        db.flush()

    # Atraso, multa acumulada (Regra 5) e suspensao automatica (Regra 2).
    for emp in list(db.scalars(select(Emprestimo).where(Emprestimo.estado.in_(ESTADOS_EMPRESTIMO_EM_ABERTO)))):
        if emp.dias_atraso > 0:
            emp.estado = EstadoEmprestimo.atrasado
            sincronizar_multa(db, emp, agora, na_devolucao=False)
            aplicar_suspensao(emp, agora)

    # Fim das suspensoes automaticas.
    for u in list(db.scalars(select(Usuario).where(
            Usuario.situacao == SituacaoUsuario.suspenso,
            Usuario.suspensao_ate.is_not(None),
            Usuario.suspensao_ate <= agora.date()))):
        u.situacao = SituacaoUsuario.ativo
        u.suspensao_ate = None
    db.flush()
