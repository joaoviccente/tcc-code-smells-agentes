from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import DIA_VENCIMENTO_FATURA, DIAS_ATRASO_BLOQUEIO_CARTAO, regra
from app.database import arredondar
from app.errors import Conflito, RegraViolada
from app.models import Cartao, Fatura
from app.services.comum import exigir_nao_encerrada, movimentar, obter, pode_debitar

EM_ABERTO = ("aberta", "fechada", "atrasada")


def vencimento_padrao(mes_referencia: str) -> date:
    ano, mes = map(int, mes_referencia.split("-"))
    ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return date(ano, mes, DIA_VENCIMENTO_FATURA)


def criar(db: Session, cartao_id: int, mes_referencia: str, valor: Decimal, vencimento: date | None) -> Fatura:
    cartao = obter(db, Cartao, cartao_id, "Cartao")
    if cartao.estado == "cancelado":
        raise Conflito("Cartao cancelado nao pode receber faturas")
    fatura = Fatura(
        cartao_id=cartao.id,
        mes_referencia=mes_referencia,
        valor=valor,
        juros=Decimal("0.00"),
        vencimento=vencimento or vencimento_padrao(mes_referencia),
        estado="aberta",
    )
    db.add(fatura)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflito(f"Ja existe fatura do cartao {cartao_id} para {mes_referencia}")
    return fatura


def atualizar_situacao(fatura: Fatura, momento: datetime) -> tuple[bool, bool]:
    """Regra 5: atraso, juros pro rata (taxa mensal / 30 por dia) e bloqueio do cartao apos 10 dias.

    Retorna (passou_a_atrasada, cartao_bloqueado).
    """
    if fatura.estado not in EM_ABERTO:
        return False, False
    dias_atraso = (momento.date() - fatura.vencimento).days
    if dias_atraso <= 0:
        return False, False
    passou = fatura.estado != "atrasada"
    fatura.estado = "atrasada"
    taxa = regra(fatura.cartao.conta.cliente.categoria).juros_atraso_mes
    fatura.juros = arredondar(fatura.valor * taxa * dias_atraso / 30)
    bloqueou = False
    if dias_atraso > DIAS_ATRASO_BLOQUEIO_CARTAO and fatura.cartao.estado == "ativo":
        fatura.cartao.estado = "bloqueado"
        bloqueou = True
    return passou, bloqueou


def listar_por_cartao(db: Session, cartao_id: int, momento: datetime) -> list[Fatura]:
    cartao = obter(db, Cartao, cartao_id, "Cartao")
    faturas = db.scalars(
        select(Fatura).where(Fatura.cartao_id == cartao.id).order_by(Fatura.mes_referencia)
    ).all()
    for f in faturas:
        atualizar_situacao(f, momento)
    db.commit()
    return list(faturas)


def obter_atualizada(db: Session, fatura_id: int, momento: datetime) -> Fatura:
    fatura = obter(db, Fatura, fatura_id, "Fatura")
    atualizar_situacao(fatura, momento)
    db.commit()
    return fatura


def fechar(db: Session, fatura_id: int, momento: datetime) -> Fatura:
    fatura = obter_atualizada(db, fatura_id, momento)
    if fatura.estado != "aberta":
        raise Conflito(f"Somente faturas abertas podem ser fechadas (estado: {fatura.estado})")
    fatura.estado = "fechada"
    db.commit()
    return fatura


def pagar(db: Session, fatura_id: int, momento: datetime) -> Fatura:
    """Paga o total devido (valor + juros) debitando a conta vinculada ao cartao."""
    fatura = obter_atualizada(db, fatura_id, momento)
    if fatura.estado == "paga":
        raise Conflito("Fatura ja paga")
    conta = fatura.cartao.conta
    exigir_nao_encerrada(conta)
    total = fatura.total_devido
    if not pode_debitar(conta, total):
        raise RegraViolada("Saldo insuficiente para pagamento da fatura")
    movimentar(conta, -total, momento)
    fatura.valor_pago = total
    fatura.pago_em = momento
    fatura.estado = "paga"
    db.commit()
    return fatura


def possui_em_aberto(db: Session, conta_id: int) -> bool:
    return (
        db.scalar(
            select(Fatura.id)
            .join(Cartao)
            .where(Cartao.conta_id == conta_id, Fatura.estado.in_(EM_ABERTO))
            .limit(1)
        )
        is not None
    )


def possui_atraso_bloqueante(db: Session, cartao: Cartao, momento: datetime) -> bool:
    for f in cartao.faturas:
        atualizar_situacao(f, momento)
        if f.estado == "atrasada" and (momento.date() - f.vencimento).days > DIAS_ATRASO_BLOQUEIO_CARTAO:
            return True
    return False
