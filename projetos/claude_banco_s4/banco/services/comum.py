from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from ..config import REGRAS, RegrasCategoria
from ..errors import NaoEncontrado, RegraViolada
from ..models import Cartao, Cliente, Conta, Fatura, Transacao

ZERO = Decimal("0.00")


def brl(valor: Decimal) -> str:
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def competencia(d: date | datetime) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def regras_do_cliente(cliente: Cliente) -> RegrasCategoria:
    return REGRAS[cliente.categoria]


def obter(db: Session, modelo, id_: int, nome: str):
    obj = db.get(modelo, id_)
    if obj is None:
        raise NaoEncontrado(f"{nome} {id_} nao encontrado(a)")
    return obj


def obter_cliente(db: Session, id_: int) -> Cliente:
    return obter(db, Cliente, id_, "Cliente")


def obter_conta(db: Session, id_: int) -> Conta:
    return obter(db, Conta, id_, "Conta")


def obter_cartao(db: Session, id_: int) -> Cartao:
    return obter(db, Cartao, id_, "Cartao")


def obter_fatura(db: Session, id_: int) -> Fatura:
    return obter(db, Fatura, id_, "Fatura")


def obter_transacao(db: Session, id_: int) -> Transacao:
    return obter(db, Transacao, id_, "Transacao")


def saldo_disponivel(conta: Conta) -> Decimal:
    return conta.saldo + conta.limite_credito


def checar_saldo(conta: Conta, debito: Decimal) -> None:
    """Regra 2: saldo pode ficar negativo ate o limite de credito, nao alem."""
    if conta.saldo - debito < -conta.limite_credito:
        raise RegraViolada(
            f"Saldo insuficiente na conta {conta.numero}: necessario {brl(debito)}, "
            f"disponivel (saldo + limite de credito) {brl(saldo_disponivel(conta))}"
        )


def aplicar_movimento(conta: Conta, delta: Decimal, momento: datetime) -> None:
    """Altera o saldo e controla desde quando a conta esta negativa (regra 6)."""
    conta.saldo = conta.saldo + delta
    if conta.saldo < 0:
        if conta.negativo_desde is None:
            conta.negativo_desde = momento
    else:
        conta.negativo_desde = None
