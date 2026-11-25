import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflito, RegraViolada
from app.models import (
    Cartao, Conta, EstadoCartao, EstadoConta, EstadoFatura, MotivoBloqueioCartao,
    SituacaoCliente,
)
from app.regras import DIAS_ATRASO_BLOQUEIO_CARTAO
from app.schemas import CartaoAtualizar, CartaoCriar
from app.services.comum import obter


def _luhn_dv(parcial: str) -> str:
    soma = 0
    for i, d in enumerate(reversed(parcial)):
        n = int(d)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        soma += n
    return str((10 - soma % 10) % 10)


def _gerar_numero(db: Session) -> str:
    while True:
        parcial = "5" + f"{secrets.randbelow(10**14):014d}"
        numero = parcial + _luhn_dv(parcial)
        if not db.scalar(select(Cartao.id).where(Cartao.numero == numero)):
            return numero


def possui_atraso_bloqueante(cartao: Cartao) -> bool:
    return any(
        f.estado == EstadoFatura.ATRASADA and f.dias_atraso > DIAS_ATRASO_BLOQUEIO_CARTAO
        for f in cartao.faturas
    )


def criar(db: Session, dados: CartaoCriar) -> Cartao:
    conta = obter(db, Conta, dados.conta_id, "Conta")
    if conta.estado != EstadoConta.ATIVA:
        raise Conflito(f"Cartao so pode ser emitido para conta ativa (conta {conta.estado.value})")
    if conta.cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("Cliente bloqueado nao pode receber cartao")
    cartao = Cartao(
        conta_id=conta.id, numero=_gerar_numero(db), limite=dados.limite,
        estado=EstadoCartao.ATIVO,
    )
    db.add(cartao)
    db.commit()
    db.refresh(cartao)
    return cartao


def atualizar(db: Session, cartao: Cartao, dados: CartaoAtualizar) -> Cartao:
    if cartao.estado == EstadoCartao.CANCELADO:
        raise Conflito("Cartao cancelado nao pode ser alterado")
    campos = dados.model_dump(exclude_unset=True)

    if campos.get("limite") is not None:
        cartao.limite = campos["limite"]

    estado = campos.get("estado")
    if estado == EstadoCartao.CANCELADO:
        raise RegraViolada("Para cancelar o cartao utilize DELETE /cartoes/{id}")
    if estado == EstadoCartao.BLOQUEADO and cartao.estado == EstadoCartao.ATIVO:
        cartao.estado = EstadoCartao.BLOQUEADO
        cartao.motivo_bloqueio = MotivoBloqueioCartao.MANUAL
    elif estado == EstadoCartao.ATIVO and cartao.estado == EstadoCartao.BLOQUEADO:
        if cartao.conta.estado != EstadoConta.ATIVA:
            raise Conflito("Conta do cartao nao esta ativa")
        if cartao.conta.cliente.situacao != SituacaoCliente.ATIVO:
            raise Conflito("Cliente do cartao esta bloqueado")
        if possui_atraso_bloqueante(cartao):
            raise Conflito(
                f"Cartao possui fatura com mais de {DIAS_ATRASO_BLOQUEIO_CARTAO} dias de atraso"
            )
        cartao.estado = EstadoCartao.ATIVO
        cartao.motivo_bloqueio = None

    db.commit()
    db.refresh(cartao)
    return cartao


def cancelar(db: Session, cartao: Cartao) -> Cartao:
    if cartao.estado == EstadoCartao.CANCELADO:
        raise Conflito("Cartao ja cancelado")
    cartao.estado = EstadoCartao.CANCELADO
    cartao.motivo_bloqueio = None
    db.commit()
    db.refresh(cartao)
    return cartao
