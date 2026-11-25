"""Funcoes utilitarias compartilhadas pelos servicos."""
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import regras
from app.enums import EstadoCartao, EstadoConta, SituacaoCliente
from app.erros import NaoEncontrado
from app.models import Cartao, Cliente, Conta

ZERO = Decimal("0.00")


def inicio_do_dia(momento: datetime) -> datetime:
    return datetime.combine(momento.date(), datetime.min.time())


def inicio_do_mes(momento: datetime | date) -> datetime:
    return datetime(momento.year, momento.month, 1)


def proximo_mes(ano: int, mes: int) -> tuple[int, int]:
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def intervalo_do_mes(momento: datetime) -> tuple[datetime, datetime]:
    ini = inicio_do_mes(momento)
    a, m = proximo_mes(ini.year, ini.month)
    return ini, datetime(a, m, 1)


def mes_referencia(momento: datetime | date) -> str:
    return f"{momento.year:04d}-{momento.month:02d}"


# ----------------------------------------------------------------- consultas

def obter_cliente(db: Session, cliente_id: int) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise NaoEncontrado(f"Cliente {cliente_id} nao encontrado")
    return cliente


def obter_conta(db: Session, conta_id: int, bloquear: bool = False) -> Conta:
    conta = db.get(Conta, conta_id, with_for_update=bloquear)
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} nao encontrada")
    return conta


def obter_cartao(db: Session, cartao_id: int) -> Cartao:
    cartao = db.get(Cartao, cartao_id)
    if cartao is None:
        raise NaoEncontrado(f"Cartao {cartao_id} nao encontrado")
    return cartao


# ------------------------------------------------------------------- saldo

def ajustar_saldo(conta: Conta, delta: Decimal, momento: datetime) -> None:
    """Altera o saldo mantendo o controle de quando ficou negativo (regra 6)."""
    conta.saldo = (conta.saldo + delta).quantize(Decimal("0.01"))
    if conta.saldo < 0:
        if conta.negativo_desde is None:
            conta.negativo_desde = momento
    else:
        conta.negativo_desde = None


def cabe_no_limite(conta: Conta, debito: Decimal) -> bool:
    """Regra 2: saldo pode ficar negativo ate o limite de credito."""
    return conta.saldo - debito >= -conta.limite_credito


# -------------------------------------------------- regra 6 (saldo negativo)

def dias_negativo(conta: Conta, hoje: date) -> int:
    if conta.negativo_desde is None or conta.saldo >= 0:
        return 0
    return (hoje - conta.negativo_desde.date()).days


def excede_prazo_negativo(conta: Conta, hoje: date) -> bool:
    return dias_negativo(conta, hoje) > regras.DIAS_SALDO_NEGATIVO_BLOQUEIO


def bloquear_cliente_e_cartoes(db: Session, cliente: Cliente) -> tuple[bool, int]:
    """Bloqueia o cliente e todos os seus cartoes nao cancelados.
    Retorna (cliente_foi_bloqueado_agora, qtd_cartoes_bloqueados)."""
    bloqueado_agora = cliente.situacao != SituacaoCliente.BLOQUEADO
    cliente.situacao = SituacaoCliente.BLOQUEADO
    cartoes = db.scalars(
        select(Cartao).join(Conta).where(
            Conta.cliente_id == cliente.id, Cartao.estado == EstadoCartao.ATIVO)
    ).all()
    for c in cartoes:
        c.estado = EstadoCartao.BLOQUEADO
    return bloqueado_agora, len(cartoes)


def aplicar_regra_saldo_negativo_cliente(db: Session, cliente: Cliente, hoje: date) -> bool:
    """Verifica (sob demanda) a regra 6 para um cliente. Se aplicada, persiste
    o bloqueio imediatamente. Retorna True se o cliente precisou ser bloqueado."""
    contas = db.scalars(select(Conta).where(
        Conta.cliente_id == cliente.id, Conta.estado != EstadoConta.ENCERRADA)).all()
    if any(excede_prazo_negativo(c, hoje) for c in contas):
        bloqueado_agora, n = bloquear_cliente_e_cartoes(db, cliente)
        if bloqueado_agora or n:
            db.commit()
        return True
    return False


# ------------------------------------------------------- geracao de numeros

def _dv_mod11(digitos: str) -> str:
    soma = sum(int(d) * p for d, p in zip(reversed(digitos), range(2, 2 + len(digitos))))
    resto = 11 - soma % 11
    return "0" if resto >= 10 else str(resto)


def gerar_numero_conta(db: Session) -> str:
    while True:
        base = f"{secrets.randbelow(10**8):08d}"
        numero = f"{base}-{_dv_mod11(base)}"
        if db.scalar(select(Conta.id).where(Conta.numero == numero)) is None:
            return numero


def _dv_luhn(parcial: str) -> str:
    total = 0
    for i, d in enumerate(reversed(parcial)):
        n = int(d)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return str((10 - total % 10) % 10)


def gerar_numero_cartao(db: Session) -> str:
    while True:
        parcial = "5" + f"{secrets.randbelow(10**14):014d}"
        numero = parcial + _dv_luhn(parcial)
        if db.scalar(select(Cartao.id).where(Cartao.numero == numero)) is None:
            return numero


def mais_de(momento: datetime, horas: int, agora: datetime) -> bool:
    return agora - momento > timedelta(hours=horas)
