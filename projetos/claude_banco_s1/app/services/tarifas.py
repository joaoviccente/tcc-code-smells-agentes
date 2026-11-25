from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import TARIFA_POR_TRANSACAO, regra
from app.models import Conta, Tarifa, Transacao
from app.services.comum import ZERO, mes_ref, movimentar, pode_debitar


def tarifa_devida_por_transacao(db: Session, conta: Conta, momento: datetime) -> Decimal:
    """Regra 3: consome a franquia mensal da categoria; esgotada, gera tarifa."""
    franquia = regra(conta.cliente.categoria).transacoes_isentas_mes
    if franquia is None:
        return ZERO
    usadas = db.scalar(
        select(func.count(Tarifa.id)).where(
            Tarifa.conta_id == conta.id,
            Tarifa.tipo == "transacao",
            Tarifa.mes_referencia == mes_ref(momento),
        )
    )
    return ZERO if usadas < franquia else TARIFA_POR_TRANSACAO


def registrar_tarifa_transacao(
    db: Session, conta: Conta, transacao: Transacao, valor_cobrado: Decimal, momento: datetime
) -> Tarifa:
    """Registra o uso da franquia (isenta) ou a tarifa cobrada, debitando a conta."""
    isenta = valor_cobrado == ZERO
    tarifa = Tarifa(
        conta_id=conta.id,
        tipo="transacao",
        valor=TARIFA_POR_TRANSACAO if isenta else valor_cobrado,
        estado="isenta" if isenta else "cobrada",
        mes_referencia=mes_ref(momento),
        transacao_id=transacao.id,
        criada_em=momento,
        cobrada_em=None if isenta else momento,
    )
    if not isenta:
        movimentar(conta, -valor_cobrado, momento)
    db.add(tarifa)
    return tarifa


def gerar_tarifa_mensal(db: Session, conta: Conta, momento: datetime) -> Tarifa | None:
    """Gera a tarifa mensal da categoria (uma por conta por mes), cobrando-a se houver saldo/limite."""
    valor = regra(conta.cliente.categoria).tarifa_mensal
    if valor <= ZERO or conta.estado == "encerrada":
        return None
    referencia = mes_ref(momento)
    existente = db.scalar(
        select(Tarifa.id).where(
            Tarifa.conta_id == conta.id, Tarifa.tipo == "mensalidade", Tarifa.mes_referencia == referencia
        )
    )
    if existente:
        return None
    tarifa = Tarifa(
        conta_id=conta.id,
        tipo="mensalidade",
        valor=valor,
        estado="pendente",
        mes_referencia=referencia,
        criada_em=momento,
    )
    db.add(tarifa)
    cobrar(conta, tarifa, momento)
    return tarifa


def cobrar(conta: Conta, tarifa: Tarifa, momento: datetime) -> bool:
    if tarifa.estado != "pendente" or not pode_debitar(conta, tarifa.valor):
        return False
    movimentar(conta, -tarifa.valor, momento)
    tarifa.estado = "cobrada"
    tarifa.cobrada_em = momento
    return True


def cobrar_pendentes(db: Session, conta: Conta, momento: datetime) -> int:
    if conta.estado == "encerrada":
        return 0
    pendentes = db.scalars(
        select(Tarifa).where(Tarifa.conta_id == conta.id, Tarifa.estado == "pendente").order_by(Tarifa.id)
    ).all()
    return sum(1 for t in pendentes if cobrar(conta, t, momento))
