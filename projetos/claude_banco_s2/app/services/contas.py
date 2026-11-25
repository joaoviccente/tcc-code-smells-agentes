import secrets
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflito, RegraViolada
from app.models import (
    Cartao, Cliente, Conta, EstadoCartao, EstadoConta, EstadoFatura, Fatura,
    SituacaoCliente, TipoConta,
)
from app.schemas import ContaAtualizar, ContaCriar
from app.services.comum import obter

FATURAS_EM_ABERTO = (EstadoFatura.ABERTA, EstadoFatura.FECHADA, EstadoFatura.ATRASADA)


def _gerar_numero(db: Session) -> str:
    while True:
        base = f"{secrets.randbelow(10**8):08d}"
        dv = sum(int(d) * (i + 2) for i, d in enumerate(reversed(base))) % 11 % 10
        numero = f"{base}-{dv}"
        if not db.scalar(select(Conta.id).where(Conta.numero == numero)):
            return numero


def criar(db: Session, dados: ContaCriar) -> Conta:
    cliente = obter(db, Cliente, dados.cliente_id, "Cliente")
    if cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("Cliente bloqueado nao pode abrir conta")
    if dados.tipo == TipoConta.POUPANCA and dados.limite_credito > 0:
        raise RegraViolada("Conta poupanca nao admite limite de credito")
    conta = Conta(
        numero=_gerar_numero(db),
        cliente_id=cliente.id,
        tipo=dados.tipo,
        saldo=Decimal("0.00"),
        limite_credito=dados.limite_credito,
        estado=EstadoConta.ATIVA,
    )
    db.add(conta)
    db.commit()
    db.refresh(conta)
    return conta


def atualizar(db: Session, conta: Conta, dados: ContaAtualizar) -> Conta:
    if conta.estado == EstadoConta.ENCERRADA:
        raise Conflito("Conta encerrada nao pode ser alterada")
    campos = dados.model_dump(exclude_unset=True)

    limite = campos.get("limite_credito")
    if limite is not None:
        if conta.tipo == TipoConta.POUPANCA and limite > 0:
            raise RegraViolada("Conta poupanca nao admite limite de credito")
        if conta.saldo < -limite:
            raise RegraViolada("Novo limite de credito e menor que o saldo devedor atual")
        conta.limite_credito = limite

    estado = campos.get("estado")
    if estado is not None:
        if estado == EstadoConta.ENCERRADA:
            raise RegraViolada("Para encerrar a conta utilize DELETE /contas/{id}")
        conta.estado = estado

    db.commit()
    db.refresh(conta)
    return conta


def encerrar(db: Session, conta: Conta, agora: datetime) -> Conta:
    """Regra 7: exige saldo zero e nenhuma fatura em aberto; cancela os cartoes."""
    if conta.estado == EstadoConta.ENCERRADA:
        raise Conflito("Conta ja encerrada")
    if conta.saldo != 0:
        raise Conflito(f"Conta so pode ser encerrada com saldo zero (saldo atual: {conta.saldo})")
    faturas_abertas = db.scalar(
        select(Fatura.id)
        .join(Cartao, Fatura.cartao_id == Cartao.id)
        .where(Cartao.conta_id == conta.id, Fatura.estado.in_(FATURAS_EM_ABERTO))
        .limit(1)
    )
    if faturas_abertas:
        raise Conflito("Conta possui fatura em aberto e nao pode ser encerrada")

    for cartao in conta.cartoes:
        cartao.estado = EstadoCartao.CANCELADO
        cartao.motivo_bloqueio = None
    conta.estado = EstadoConta.ENCERRADA
    conta.encerrada_em = agora
    db.commit()
    db.refresh(conta)
    return conta
