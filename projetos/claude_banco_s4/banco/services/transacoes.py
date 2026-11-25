"""Deposito, saque, transferencia, estorno e extrato (regras 1 a 4)."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import clock
from ..config import PRAZO_ESTORNO, TARIFA_POR_TRANSACAO
from ..enums import (
    EstadoConta,
    EstadoTarifa,
    EstadoTransacao,
    SituacaoCliente,
    TipoTarifa,
    TipoTransacao,
)
from ..errors import Conflito, RegraViolada
from ..models import Conta, Tarifa, Transacao
from .comum import (
    ZERO,
    aplicar_movimento,
    brl,
    checar_saldo,
    competencia,
    obter_conta,
    obter_transacao,
    regras_do_cliente,
)


class ResultadoOperacao:
    def __init__(self, transacao: Transacao, tarifa: Tarifa | None, contas: list[Conta]):
        self.transacao = transacao
        self.tarifa = tarifa
        self.saldos = {c.id: c.saldo for c in contas}


# ------------------------------------------------------------------ validacoes
def _validar_conta_para_debito(conta: Conta) -> None:
    """Regra 1: conta ativa de cliente ativo."""
    if conta.estado != EstadoConta.ATIVA:
        raise Conflito(f"Conta {conta.numero} nao esta ativa (estado: {conta.estado.value})")
    if conta.cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito(f"Cliente da conta {conta.numero} esta bloqueado")


def _validar_conta_para_credito(conta: Conta) -> None:
    if conta.estado != EstadoConta.ATIVA:
        raise Conflito(f"Conta {conta.numero} nao esta ativa (estado: {conta.estado.value})")


def total_sacado_no_dia(db: Session, cliente_id: int, momento: datetime) -> Decimal:
    inicio = datetime.combine(momento.date(), time.min)
    fim = inicio + timedelta(days=1)
    total = db.scalar(
        select(func.sum(Transacao.valor))
        .join(Conta, Transacao.conta_id == Conta.id)
        .where(
            Conta.cliente_id == cliente_id,
            Transacao.tipo == TipoTransacao.SAQUE,
            Transacao.estado == EstadoTransacao.EFETIVADA,
            Transacao.data >= inicio,
            Transacao.data < fim,
        )
    )
    return total or ZERO


# ------------------------------------------------------------------ tarifas por transacao
def _tarifa_da_transacao(db: Session, conta: Conta, momento: datetime) -> Tarifa:
    """Regra 3: consome a franquia mensal da categoria; esgotada, gera tarifa."""
    regras = regras_do_cliente(conta.cliente)
    comp = competencia(momento)
    base = dict(conta=conta, tipo=TipoTarifa.TRANSACAO, competencia=comp, data=momento)
    if regras.transacoes_isentas_mes is None:
        return Tarifa(**base, valor=ZERO, estado=EstadoTarifa.ISENTA,
                      descricao="Categoria com transacoes isentas ilimitadas")
    usadas = db.scalar(
        select(func.count(Tarifa.id)).where(
            Tarifa.conta_id == conta.id, Tarifa.tipo == TipoTarifa.TRANSACAO, Tarifa.competencia == comp
        )
    ) or 0
    if usadas < regras.transacoes_isentas_mes:
        return Tarifa(**base, valor=ZERO, estado=EstadoTarifa.ISENTA,
                      descricao=f"Franquia mensal ({usadas + 1}/{regras.transacoes_isentas_mes})")
    return Tarifa(**base, valor=TARIFA_POR_TRANSACAO, estado=EstadoTarifa.COBRADA, data_cobranca=momento,
                  descricao="Transacao excedente a franquia mensal")


def _registrar(db: Session, transacao: Transacao, tarifa: Tarifa | None, momento: datetime) -> None:
    db.add(transacao)
    db.flush()
    if tarifa is not None:
        tarifa.transacao_id = transacao.id
        db.add(tarifa)
        if tarifa.estado == EstadoTarifa.COBRADA:
            aplicar_movimento(tarifa.conta, -tarifa.valor, momento)
    transacao.estado = EstadoTransacao.EFETIVADA


# ------------------------------------------------------------------ operacoes
def depositar(db: Session, conta_id: int, valor: Decimal, descricao: str | None) -> ResultadoOperacao:
    agora = clock.agora()
    conta = obter_conta(db, conta_id)
    _validar_conta_para_credito(conta)
    t = Transacao(conta_id=conta.id, tipo=TipoTransacao.DEPOSITO, valor=valor, data=agora,
                  estado=EstadoTransacao.PENDENTE, descricao=descricao)
    aplicar_movimento(conta, valor, agora)
    _registrar(db, t, None, agora)
    db.commit()
    return ResultadoOperacao(t, None, [conta])


def sacar(db: Session, conta_id: int, valor: Decimal, descricao: str | None) -> ResultadoOperacao:
    agora = clock.agora()
    conta = obter_conta(db, conta_id)
    _validar_conta_para_debito(conta)
    regras = regras_do_cliente(conta.cliente)
    ja_sacado = total_sacado_no_dia(db, conta.cliente_id, agora)
    if ja_sacado + valor > regras.limite_diario_saque:
        disponivel = max(ZERO, regras.limite_diario_saque - ja_sacado)
        raise RegraViolada(
            f"Limite diario de saque da categoria {conta.cliente.categoria.value} "
            f"({brl(regras.limite_diario_saque)}) excedido: ja sacado hoje {brl(ja_sacado)}, "
            f"disponivel {brl(disponivel)}"
        )
    tarifa = _tarifa_da_transacao(db, conta, agora)
    checar_saldo(conta, valor + tarifa.valor)
    t = Transacao(conta_id=conta.id, tipo=TipoTransacao.SAQUE, valor=valor, data=agora,
                  estado=EstadoTransacao.PENDENTE, descricao=descricao)
    aplicar_movimento(conta, -valor, agora)
    _registrar(db, t, tarifa, agora)
    db.commit()
    return ResultadoOperacao(t, tarifa, [conta])


def transferir(db: Session, origem_id: int, destino_id: int, valor: Decimal,
               descricao: str | None) -> ResultadoOperacao:
    if origem_id == destino_id:
        raise RegraViolada("Conta de origem e destino devem ser diferentes")
    agora = clock.agora()
    origem = obter_conta(db, origem_id)
    destino = obter_conta(db, destino_id)
    _validar_conta_para_debito(origem)
    _validar_conta_para_credito(destino)
    regras = regras_do_cliente(origem.cliente)
    if valor > regras.limite_por_transferencia:
        raise RegraViolada(
            f"Valor excede o limite por transferencia da categoria {origem.cliente.categoria.value} "
            f"({brl(regras.limite_por_transferencia)})"
        )
    if origem.cliente_id == destino.cliente_id:
        tarifa = Tarifa(conta=origem, tipo=TipoTarifa.TRANSFERENCIA_MESMO_TITULAR, valor=ZERO,
                        estado=EstadoTarifa.ISENTA, competencia=competencia(agora), data=agora,
                        descricao="Transferencia entre contas do mesmo cliente")
    else:
        tarifa = _tarifa_da_transacao(db, origem, agora)
    checar_saldo(origem, valor + tarifa.valor)
    t = Transacao(conta_id=origem.id, conta_destino_id=destino.id, tipo=TipoTransacao.TRANSFERENCIA,
                  valor=valor, data=agora, estado=EstadoTransacao.PENDENTE, descricao=descricao)
    aplicar_movimento(origem, -valor, agora)
    aplicar_movimento(destino, valor, agora)
    _registrar(db, t, tarifa, agora)
    db.commit()
    return ResultadoOperacao(t, tarifa, [origem, destino])


def estornar(db: Session, transacao_id: int, descricao: str | None = None) -> ResultadoOperacao:
    """Regra 4: estorno de transacao efetivada em ate 24h, revertendo os saldos."""
    agora = clock.agora()
    original = obter_transacao(db, transacao_id)
    if original.tipo == TipoTransacao.ESTORNO:
        raise Conflito("Uma transacao de estorno nao pode ser estornada")
    if original.estado == EstadoTransacao.ESTORNADA:
        raise Conflito("Transacao ja foi estornada")
    if original.estado != EstadoTransacao.EFETIVADA:
        raise Conflito(f"Apenas transacoes efetivadas podem ser estornadas (estado: {original.estado.value})")
    if agora - original.data > PRAZO_ESTORNO:
        raise RegraViolada("Prazo de estorno expirado: permitido somente em ate 24 horas da transacao")

    conta = original.conta
    destino = original.conta_destino
    envolvidas = [c for c in (conta, destino) if c is not None]
    for c in envolvidas:
        if c.estado == EstadoConta.ENCERRADA:
            raise Conflito(f"Conta {c.numero} esta encerrada; estorno nao permitido")

    # Movimentos de reversao: (conta, delta)
    if original.tipo == TipoTransacao.DEPOSITO:
        movimentos = [(conta, -original.valor)]
    elif original.tipo == TipoTransacao.SAQUE:
        movimentos = [(conta, original.valor)]
    else:  # transferencia
        movimentos = [(conta, original.valor), (destino, -original.valor)]
    for c, delta in movimentos:
        if delta < 0:
            checar_saldo(c, -delta)

    estorno = Transacao(conta_id=original.conta_id, conta_destino_id=original.conta_destino_id,
                        tipo=TipoTransacao.ESTORNO, valor=original.valor, data=agora,
                        estado=EstadoTransacao.PENDENTE, transacao_original_id=original.id,
                        descricao=descricao or f"Estorno da transacao {original.id} ({original.tipo.value})")
    for c, delta in movimentos:
        aplicar_movimento(c, delta, agora)
    original.estado = EstadoTransacao.ESTORNADA
    _registrar(db, estorno, None, agora)
    db.commit()
    return ResultadoOperacao(estorno, None, envolvidas)


# ------------------------------------------------------------------ extrato
def efeito_na_conta(t: Transacao, conta_id: int) -> Decimal:
    """Variacao de saldo que a transacao causou na conta informada."""
    if t.tipo == TipoTransacao.DEPOSITO:
        return t.valor
    if t.tipo == TipoTransacao.SAQUE:
        return -t.valor
    if t.tipo == TipoTransacao.TRANSFERENCIA:
        return -t.valor if t.conta_id == conta_id else t.valor
    raise ValueError("Estorno: use o efeito inverso da transacao original")


def extrato(db: Session, conta_id: int, inicio: datetime | None, fim: datetime | None):
    conta = obter_conta(db, conta_id)
    q = select(Transacao).where(or_(Transacao.conta_id == conta.id, Transacao.conta_destino_id == conta.id))
    if inicio:
        q = q.where(Transacao.data >= inicio)
    if fim:
        q = q.where(Transacao.data <= fim)
    transacoes = list(db.scalars(q.order_by(Transacao.data, Transacao.id)))
    itens = []
    for t in transacoes:
        if t.tipo == TipoTransacao.ESTORNO:
            original = db.get(Transacao, t.transacao_original_id)
            efeito = -efeito_na_conta(original, conta.id)
        else:
            efeito = efeito_na_conta(t, conta.id)
        itens.append({"transacao": t, "efeito": efeito})
    return conta, itens
