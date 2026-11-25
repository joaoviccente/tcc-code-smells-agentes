from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.errors import Conflito, RegraViolada
from app.models import (
    Conta, EstadoConta, EstadoTransacao, SituacaoCliente, TipoTransacao, Transacao,
)
from app.regras import PRAZO_ESTORNO, REGRAS
from app.services import clientes as clientes_service
from app.services import tarifas as tarifas_service
from app.services.comum import movimentar_saldo, negativo_prolongado, obter, pode_debitar


# ------------------------------------------------------------------ apoio
def _exigir_conta_operavel(db: Session, conta: Conta, agora: datetime) -> None:
    """Regra 1: saque/transferencia apenas em conta ativa de cliente ativo.

    Avalia tambem, de forma tardia, a regra 6 (saldo negativo > 30 dias),
    persistindo o bloqueio antes de recusar a operacao.
    """
    cliente = conta.cliente
    if cliente.situacao == SituacaoCliente.ATIVO and any(
        negativo_prolongado(c, agora) for c in cliente.contas
    ):
        clientes_service.bloquear_por_saldo_negativo(cliente)
        db.commit()
        raise Conflito("Cliente bloqueado: conta com saldo negativo ha mais de 30 dias")
    if cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("Operacao nao permitida: cliente bloqueado")
    if conta.estado != EstadoConta.ATIVA:
        raise Conflito(f"Operacao nao permitida: conta {conta.estado.value}")


def _exigir_nao_encerrada(conta: Conta) -> None:
    if conta.estado == EstadoConta.ENCERRADA:
        raise Conflito(f"Conta {conta.id} esta encerrada")


def _exigir_saldo(conta: Conta, valor: Decimal) -> None:
    if not pode_debitar(conta, valor):
        disponivel = conta.saldo + conta.limite_credito
        raise RegraViolada(
            f"Saldo insuficiente: disponivel (saldo + limite de credito) {disponivel}"
        )


def _total_sacado_no_dia(db: Session, cliente_id: int, dia: date) -> Decimal:
    inicio = datetime.combine(dia, time.min)
    total = db.scalar(
        select(func.coalesce(func.sum(Transacao.valor), 0))
        .join(Conta, Transacao.conta_id == Conta.id)
        .where(
            Conta.cliente_id == cliente_id,
            Transacao.tipo == TipoTransacao.SAQUE,
            Transacao.estado == EstadoTransacao.EFETIVADA,
            Transacao.data >= inicio,
            Transacao.data < inicio + timedelta(days=1),
        )
    )
    return Decimal(total or 0)


# -------------------------------------------------------------- operacoes
def depositar(db: Session, conta_id: int, valor: Decimal, descricao: str | None,
              agora: datetime) -> Transacao:
    conta = obter(db, Conta, conta_id, "Conta")
    _exigir_nao_encerrada(conta)
    movimentar_saldo(conta, valor, agora)
    transacao = Transacao(
        conta_id=conta.id, tipo=TipoTransacao.DEPOSITO, valor=valor, data=agora,
        estado=EstadoTransacao.EFETIVADA, descricao=descricao,
    )
    db.add(transacao)
    db.commit()
    db.refresh(transacao)
    return transacao


def sacar(db: Session, conta_id: int, valor: Decimal, descricao: str | None,
          agora: datetime) -> Transacao:
    conta = obter(db, Conta, conta_id, "Conta")
    _exigir_conta_operavel(db, conta, agora)

    regras = REGRAS[conta.cliente.categoria]
    ja_sacado = _total_sacado_no_dia(db, conta.cliente_id, agora.date())
    if ja_sacado + valor > regras.limite_saque_diario:
        raise RegraViolada(
            f"Limite diario de saque excedido: limite {regras.limite_saque_diario}, "
            f"ja sacado hoje {ja_sacado}, disponivel {regras.limite_saque_diario - ja_sacado}"
        )
    _exigir_saldo(conta, valor)

    movimentar_saldo(conta, -valor, agora)
    transacao = Transacao(
        conta_id=conta.id, tipo=TipoTransacao.SAQUE, valor=valor, data=agora,
        estado=EstadoTransacao.EFETIVADA, descricao=descricao,
    )
    db.add(transacao)
    tarifas_service.registrar_tarifa_transacao(db, conta, transacao, agora)
    db.commit()
    db.refresh(transacao)
    return transacao


def transferir(db: Session, origem_id: int, destino_id: int, valor: Decimal,
               descricao: str | None, agora: datetime) -> Transacao:
    if origem_id == destino_id:
        raise RegraViolada("Conta de origem e destino devem ser diferentes")
    origem = obter(db, Conta, origem_id, "Conta de origem")
    destino = obter(db, Conta, destino_id, "Conta de destino")
    _exigir_conta_operavel(db, origem, agora)
    _exigir_nao_encerrada(destino)

    regras = REGRAS[origem.cliente.categoria]
    if valor > regras.limite_por_transferencia:
        raise RegraViolada(
            f"Valor excede o limite por transferencia da categoria "
            f"{origem.cliente.categoria.value}: {regras.limite_por_transferencia}"
        )
    _exigir_saldo(origem, valor)

    movimentar_saldo(origem, -valor, agora)
    movimentar_saldo(destino, valor, agora)
    transacao = Transacao(
        conta_id=origem.id, conta_destino_id=destino.id, tipo=TipoTransacao.TRANSFERENCIA,
        valor=valor, data=agora, estado=EstadoTransacao.EFETIVADA, descricao=descricao,
    )
    db.add(transacao)
    # Regra 3: entre contas do mesmo cliente e isenta (nao consome franquia)
    if origem.cliente_id != destino.cliente_id:
        tarifas_service.registrar_tarifa_transacao(db, origem, transacao, agora)
    db.commit()
    db.refresh(transacao)
    return transacao


def estornar(db: Session, transacao_id: int, agora: datetime) -> Transacao:
    """Regra 4: estorno de transacao efetivada em ate 24 horas."""
    original = obter(db, Transacao, transacao_id, "Transacao")
    if original.tipo == TipoTransacao.ESTORNO:
        raise RegraViolada("Uma transacao de estorno nao pode ser estornada")
    if original.estado != EstadoTransacao.EFETIVADA:
        raise Conflito(f"Somente transacoes efetivadas podem ser estornadas "
                       f"(estado atual: {original.estado.value})")
    if agora - original.data > PRAZO_ESTORNO:
        raise RegraViolada("Prazo de estorno expirado (24 horas apos a transacao)")

    conta = original.conta
    _exigir_nao_encerrada(conta)
    valor = original.valor
    if original.tipo == TipoTransacao.DEPOSITO:
        _exigir_saldo(conta, valor)
        movimentar_saldo(conta, -valor, agora)
    elif original.tipo == TipoTransacao.SAQUE:
        movimentar_saldo(conta, valor, agora)
    else:  # transferencia
        destino = original.conta_destino
        _exigir_nao_encerrada(destino)
        _exigir_saldo(destino, valor)
        movimentar_saldo(destino, -valor, agora)
        movimentar_saldo(conta, valor, agora)

    original.estado = EstadoTransacao.ESTORNADA
    estorno = Transacao(
        conta_id=original.conta_id, conta_destino_id=original.conta_destino_id,
        tipo=TipoTransacao.ESTORNO, valor=valor, data=agora,
        estado=EstadoTransacao.EFETIVADA, transacao_original_id=original.id,
        descricao=f"Estorno da transacao {original.id}",
    )
    db.add(estorno)
    db.commit()
    db.refresh(estorno)
    return estorno


# ---------------------------------------------------------------- extrato
def efeito_na_conta(transacao: Transacao, conta_id: int) -> Decimal:
    v = transacao.valor
    match transacao.tipo:
        case TipoTransacao.DEPOSITO:
            return v
        case TipoTransacao.SAQUE:
            return -v
        case TipoTransacao.TRANSFERENCIA:
            return -v if transacao.conta_id == conta_id else v
        case TipoTransacao.ESTORNO:
            return -efeito_na_conta(transacao.original, conta_id)


def extrato(db: Session, conta: Conta, inicio: date | None, fim: date | None) -> list[Transacao]:
    q = select(Transacao).where(
        or_(Transacao.conta_id == conta.id, Transacao.conta_destino_id == conta.id)
    )
    if inicio:
        q = q.where(Transacao.data >= datetime.combine(inicio, time.min))
    if fim:
        q = q.where(Transacao.data < datetime.combine(fim + timedelta(days=1), time.min))
    return list(db.scalars(q.order_by(Transacao.data, Transacao.id)))
