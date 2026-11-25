"""Funcoes compartilhadas entre os servicos."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.errors import NaoEncontrado, RegraViolada
from app.models import Cliente, Conta, EstadoCartao


def obter(db: Session, modelo, ident: int, nome: str):
    obj = db.get(modelo, ident)
    if obj is None:
        raise NaoEncontrado(nome, ident)
    return obj


def ajustar_saldo(conta: Conta, delta: Decimal, momento: datetime) -> None:
    """Aplica um movimento ao saldo e mantem o controle de 'negativo_desde'."""
    conta.saldo = conta.saldo + delta
    if conta.saldo < 0:
        if conta.negativo_desde is None:
            conta.negativo_desde = momento
    else:
        conta.negativo_desde = None


def garantir_saldo(conta: Conta, valor: Decimal) -> None:
    """Regra 2: saldo pode ficar negativo ate o limite de credito, nunca abaixo."""
    if conta.saldo - valor < -conta.limite_credito:
        raise RegraViolada(
            "saldo_insuficiente",
            f"Saldo insuficiente na conta {conta.numero}: disponivel {conta.saldo_disponivel}, "
            f"necessario {valor}.",
        )


def bloquear_cartoes_do_cliente(cliente: Cliente, motivo: str) -> int:
    n = 0
    for conta in cliente.contas:
        for cartao in conta.cartoes:
            if cartao.estado == EstadoCartao.ATIVO:
                cartao.estado = EstadoCartao.BLOQUEADO
                cartao.motivo_bloqueio = motivo
                n += 1
    return n
