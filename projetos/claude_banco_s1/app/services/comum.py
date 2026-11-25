from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DIAS_NEGATIVO_BLOQUEIO_CLIENTE
from app.database import arredondar
from app.errors import Conflito, NaoEncontrado
from app.models import Cartao, Cliente, Conta

ZERO = Decimal("0.00")


def obter(db: Session, modelo, id_: int, nome: str):
    obj = db.get(modelo, id_)
    if obj is None:
        raise NaoEncontrado(f"{nome} {id_} nao encontrado(a)")
    return obj


def mes_ref(momento: datetime) -> str:
    return momento.strftime("%Y-%m")


def inicio_do_dia(momento: datetime) -> datetime:
    return momento.replace(hour=0, minute=0, second=0, microsecond=0)


def fim_do_dia(momento: datetime) -> datetime:
    return inicio_do_dia(momento) + timedelta(days=1)


def pode_debitar(conta: Conta, valor: Decimal) -> bool:
    """Regra 2: o saldo pode ficar negativo ate o limite de credito da conta."""
    return conta.saldo - valor >= -conta.limite_credito


def movimentar(conta: Conta, delta: Decimal, momento: datetime) -> None:
    """Aplica um credito (delta > 0) ou debito (delta < 0) e controla o inicio do saldo negativo."""
    conta.saldo = arredondar(conta.saldo + delta)
    if conta.saldo < ZERO:
        if conta.negativo_desde is None:
            conta.negativo_desde = momento
    else:
        conta.negativo_desde = None


def negativo_excedido(conta: Conta, momento: datetime) -> bool:
    return (
        conta.negativo_desde is not None
        and conta.saldo < ZERO
        and momento - conta.negativo_desde > timedelta(days=DIAS_NEGATIVO_BLOQUEIO_CLIENTE)
    )


def bloquear_cliente_e_cartoes(db: Session, cliente: Cliente) -> int:
    """Regra 6: bloqueia o cliente e todos os seus cartoes ativos. Retorna cartoes bloqueados."""
    cliente.situacao = "bloqueado"
    cartoes = db.scalars(
        select(Cartao).join(Conta).where(Conta.cliente_id == cliente.id, Cartao.estado == "ativo")
    ).all()
    for cartao in cartoes:
        cartao.estado = "bloqueado"
    return len(cartoes)


def aplicar_regra_negativo(db: Session, cliente: Cliente, momento: datetime) -> bool:
    """Avalia a regra 6 para um cliente. Retorna True se o cliente foi bloqueado agora."""
    if cliente.situacao == "bloqueado":
        return False
    if any(negativo_excedido(c, momento) for c in cliente.contas):
        bloquear_cliente_e_cartoes(db, cliente)
        return True
    return False


def exigir_operavel(db: Session, conta: Conta, momento: datetime) -> None:
    """Regra 1: saque e transferencia apenas em conta ativa de cliente ativo."""
    if aplicar_regra_negativo(db, conta.cliente, momento):
        # Persiste o bloqueio antes de recusar a operacao.
        db.commit()
    if conta.estado != "ativa":
        raise Conflito(f"Conta {conta.id} nao esta ativa (estado: {conta.estado})")
    if conta.cliente.situacao != "ativo":
        raise Conflito(f"Cliente {conta.cliente_id} esta bloqueado")


def exigir_nao_encerrada(conta: Conta) -> None:
    if conta.estado == "encerrada":
        raise Conflito(f"Conta {conta.id} esta encerrada")
