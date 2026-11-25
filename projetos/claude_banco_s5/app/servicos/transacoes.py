"""Deposito, saque, transferencia, estorno e extrato (regras 1 a 4)."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import clock, regras
from app.enums import (
    EstadoConta, EstadoTransacao, SituacaoCliente, TipoTransacao,
)
from app.erros import Conflito, NaoEncontrado, RegraNegocio
from app.models import Conta, Tarifa, Transacao
from app.schemas import DepositoIn, SaqueIn, TransferenciaIn
from app.servicos.comum import (
    ZERO, ajustar_saldo, aplicar_regra_saldo_negativo_cliente, cabe_no_limite,
    inicio_do_dia, mais_de, obter_conta,
)
from app.servicos.tarifas import cobrar_pendentes_da_conta, registrar_tarifa_transacao


def _exigir_conta_ativa(conta: Conta, papel: str = "Conta") -> None:
    if conta.estado != EstadoConta.ATIVA:
        raise Conflito(f"{papel} {conta.numero} nao esta ativa (estado: {conta.estado.value})")


def _exigir_cliente_ativo(conta: Conta) -> None:
    if conta.cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("Cliente titular da conta esta bloqueado")


def _exigir_saldo(conta: Conta, valor: Decimal) -> None:
    if not cabe_no_limite(conta, valor):
        disponivel = conta.saldo + conta.limite_credito
        raise RegraNegocio(
            f"Saldo insuficiente: disponivel (saldo + limite de credito) = {disponivel}")


def _nova_transacao(db: Session, **kw) -> Transacao:
    t = Transacao(**kw)
    db.add(t)
    db.flush()
    return t


def _resultado(transacao: Transacao, tarifa: Optional[Tarifa], conta: Conta) -> dict:
    return {"transacao": transacao, "tarifa": tarifa, "saldo_conta": conta.saldo}


# ------------------------------------------------------------------ deposito

def depositar(db: Session, dados: DepositoIn) -> dict:
    agora = clock.agora()
    conta = obter_conta(db, dados.conta_id, bloquear=True)
    _exigir_conta_ativa(conta)
    t = _nova_transacao(db, conta_id=conta.id, tipo=TipoTransacao.DEPOSITO, valor=dados.valor,
                        data=agora, estado=EstadoTransacao.EFETIVADA, descricao=dados.descricao)
    ajustar_saldo(conta, dados.valor, agora)
    cobrar_pendentes_da_conta(db, conta, agora)
    db.commit()
    return _resultado(t, None, conta)


# --------------------------------------------------------------------- saque

def total_sacado_no_dia(db: Session, cliente_id: int, agora: datetime) -> Decimal:
    """Soma dos saques efetivados do cliente no dia (todas as suas contas)."""
    total = db.scalar(
        select(func.sum(Transacao.valor)).join(Conta, Conta.id == Transacao.conta_id).where(
            Conta.cliente_id == cliente_id,
            Transacao.tipo == TipoTransacao.SAQUE,
            Transacao.estado == EstadoTransacao.EFETIVADA,
            Transacao.data >= inicio_do_dia(agora), Transacao.data <= agora))
    return total or ZERO


def sacar(db: Session, dados: SaqueIn) -> dict:
    agora = clock.agora()
    conta = obter_conta(db, dados.conta_id)
    aplicar_regra_saldo_negativo_cliente(db, conta.cliente, agora.date())
    conta = obter_conta(db, dados.conta_id, bloquear=True)
    _exigir_conta_ativa(conta)
    _exigir_cliente_ativo(conta)

    regra = regras.regra(conta.cliente.categoria)
    ja_sacado = total_sacado_no_dia(db, conta.cliente_id, agora)
    if ja_sacado + dados.valor > regra.limite_diario_saque:
        raise RegraNegocio(
            f"Limite diario de saque excedido para a categoria {conta.cliente.categoria.value}: "
            f"limite {regra.limite_diario_saque}, ja sacado hoje {ja_sacado}, "
            f"disponivel {regra.limite_diario_saque - ja_sacado}")
    _exigir_saldo(conta, dados.valor)

    t = _nova_transacao(db, conta_id=conta.id, tipo=TipoTransacao.SAQUE, valor=dados.valor,
                        data=agora, estado=EstadoTransacao.EFETIVADA, descricao=dados.descricao)
    ajustar_saldo(conta, -dados.valor, agora)
    tarifa = registrar_tarifa_transacao(db, conta, t, agora)
    db.commit()
    return _resultado(t, tarifa, conta)


# ------------------------------------------------------------- transferencia

def transferir(db: Session, dados: TransferenciaIn) -> dict:
    if dados.conta_origem_id == dados.conta_destino_id:
        raise RegraNegocio("Conta de origem e destino devem ser diferentes")
    agora = clock.agora()
    origem = obter_conta(db, dados.conta_origem_id)
    obter_conta(db, dados.conta_destino_id)
    aplicar_regra_saldo_negativo_cliente(db, origem.cliente, agora.date())

    # trava as contas em ordem de id para evitar deadlock
    ids = sorted([dados.conta_origem_id, dados.conta_destino_id])
    travadas = {i: obter_conta(db, i, bloquear=True) for i in ids}
    origem, destino = travadas[dados.conta_origem_id], travadas[dados.conta_destino_id]

    _exigir_conta_ativa(origem, "Conta de origem")
    _exigir_cliente_ativo(origem)
    _exigir_conta_ativa(destino, "Conta de destino")

    regra = regras.regra(origem.cliente.categoria)
    if dados.valor > regra.limite_por_transferencia:
        raise RegraNegocio(
            f"Valor excede o limite por transferencia da categoria "
            f"{origem.cliente.categoria.value}: {regra.limite_por_transferencia}")
    _exigir_saldo(origem, dados.valor)

    t = _nova_transacao(db, conta_id=origem.id, conta_destino_id=destino.id,
                        tipo=TipoTransacao.TRANSFERENCIA, valor=dados.valor, data=agora,
                        estado=EstadoTransacao.EFETIVADA, descricao=dados.descricao)
    ajustar_saldo(origem, -dados.valor, agora)
    ajustar_saldo(destino, dados.valor, agora)

    tarifa = None
    if origem.cliente_id != destino.cliente_id:  # mesmo titular: isenta e sem franquia
        tarifa = registrar_tarifa_transacao(db, origem, t, agora)
    cobrar_pendentes_da_conta(db, destino, agora)
    db.commit()
    return _resultado(t, tarifa, origem)


# ------------------------------------------------------------------- estorno

def obter_transacao(db: Session, transacao_id: int) -> Transacao:
    t = db.get(Transacao, transacao_id)
    if t is None:
        raise NaoEncontrado(f"Transacao {transacao_id} nao encontrada")
    return t


def estornar(db: Session, transacao_id: int, descricao: Optional[str]) -> dict:
    """Regra 4: transacao efetivada pode ser estornada em ate 24 horas."""
    agora = clock.agora()
    original = obter_transacao(db, transacao_id)
    if original.tipo == TipoTransacao.ESTORNO:
        raise Conflito("Uma transacao de estorno nao pode ser estornada")
    if original.estado == EstadoTransacao.ESTORNADA:
        raise Conflito("Transacao ja foi estornada")
    if original.estado != EstadoTransacao.EFETIVADA:
        raise Conflito("Somente transacoes efetivadas podem ser estornadas")
    if mais_de(original.data, regras.PRAZO_ESTORNO_HORAS, agora):
        raise RegraNegocio(
            f"Prazo para estorno expirado ({regras.PRAZO_ESTORNO_HORAS} horas apos a transacao)")

    ids = sorted({i for i in (original.conta_id, original.conta_destino_id) if i})
    contas = {i: obter_conta(db, i, bloquear=True) for i in ids}
    for c in contas.values():
        if c.estado == EstadoConta.ENCERRADA:
            raise Conflito(f"Conta {c.numero} esta encerrada; estorno nao permitido")

    conta = contas[original.conta_id]
    v = original.valor
    if original.tipo == TipoTransacao.DEPOSITO:
        if not cabe_no_limite(conta, v):
            raise RegraNegocio("Saldo insuficiente para estornar o deposito")
        ajustar_saldo(conta, -v, agora)
    elif original.tipo == TipoTransacao.SAQUE:
        ajustar_saldo(conta, v, agora)
    else:  # transferencia
        destino = contas[original.conta_destino_id]
        if not cabe_no_limite(destino, v):
            raise RegraNegocio("Saldo insuficiente na conta de destino para estornar a transferencia")
        ajustar_saldo(destino, -v, agora)
        ajustar_saldo(conta, v, agora)

    original.estado = EstadoTransacao.ESTORNADA
    estorno = _nova_transacao(
        db, conta_id=original.conta_id, conta_destino_id=original.conta_destino_id,
        tipo=TipoTransacao.ESTORNO, valor=v, data=agora, estado=EstadoTransacao.EFETIVADA,
        descricao=descricao or f"Estorno da transacao {original.id}",
        transacao_original_id=original.id)
    db.commit()
    return {"estorno": estorno, "transacao_original": original}


# ------------------------------------------------------------------- extrato

def _natureza(t: Transacao, conta_id: int, tipo_original: Optional[TipoTransacao]) -> str:
    origem = t.conta_id == conta_id
    if t.tipo == TipoTransacao.DEPOSITO:
        return "credito"
    if t.tipo == TipoTransacao.SAQUE:
        return "debito"
    if t.tipo == TipoTransacao.TRANSFERENCIA:
        return "debito" if origem else "credito"
    # estorno: inverte o efeito da transacao original
    if tipo_original == TipoTransacao.DEPOSITO:
        return "debito"
    if tipo_original == TipoTransacao.SAQUE:
        return "credito"
    return "credito" if origem else "debito"


def extrato(db: Session, conta_id: int, inicio: Optional[datetime],
            fim: Optional[datetime], tipo: Optional[TipoTransacao]) -> dict:
    conta = obter_conta(db, conta_id)
    q = select(Transacao).where(
        or_(Transacao.conta_id == conta_id, Transacao.conta_destino_id == conta_id))
    if inicio:
        q = q.where(Transacao.data >= inicio)
    if fim:
        q = q.where(Transacao.data <= fim)
    if tipo:
        q = q.where(Transacao.tipo == tipo)
    transacoes = list(db.scalars(q.order_by(Transacao.data, Transacao.id)))

    ids_orig = {t.transacao_original_id for t in transacoes if t.transacao_original_id}
    tipos_orig = dict(db.execute(
        select(Transacao.id, Transacao.tipo).where(Transacao.id.in_(ids_orig))).all()) if ids_orig else {}

    lancamentos = []
    for t in transacoes:
        if t.conta_destino_id is None:
            contraparte = None
        else:
            contraparte = t.conta_destino_id if t.conta_id == conta_id else t.conta_id
        lancamentos.append({
            "transacao_id": t.id, "data": t.data, "tipo": t.tipo, "estado": t.estado,
            "descricao": t.descricao,
            "natureza": _natureza(t, conta_id, tipos_orig.get(t.transacao_original_id)),
            "valor": t.valor, "conta_contraparte_id": contraparte,
            "transacao_original_id": t.transacao_original_id,
        })
    qt = select(Tarifa).where(Tarifa.conta_id == conta_id, Tarifa.cobrada_em.is_not(None))
    if inicio:
        qt = qt.where(Tarifa.cobrada_em >= inicio)
    if fim:
        qt = qt.where(Tarifa.cobrada_em <= fim)
    tarifas = list(db.scalars(qt.order_by(Tarifa.cobrada_em, Tarifa.id)))
    return {"conta_id": conta.id, "numero": conta.numero, "saldo_atual": conta.saldo,
            "inicio": inicio, "fim": fim, "lancamentos": lancamentos,
            "tarifas_cobradas": tarifas}
