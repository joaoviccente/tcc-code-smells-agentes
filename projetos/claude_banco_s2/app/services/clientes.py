from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflito
from app.models import (
    Cliente, EstadoCartao, EstadoConta, MotivoBloqueioCartao, SituacaoCliente,
)
from app.schemas import ClienteAtualizar, ClienteCriar
from app.services.comum import negativo_prolongado


def _garantir_unicidade(db: Session, cpf: str | None, email: str | None, ignorar_id=None):
    if cpf is not None:
        existente = db.scalar(select(Cliente).where(Cliente.cpf == cpf))
        if existente and existente.id != ignorar_id:
            raise Conflito("Ja existe cliente com este CPF")
    if email is not None:
        existente = db.scalar(select(Cliente).where(Cliente.email == email))
        if existente and existente.id != ignorar_id:
            raise Conflito("Ja existe cliente com este e-mail")


def criar(db: Session, dados: ClienteCriar) -> Cliente:
    _garantir_unicidade(db, dados.cpf, dados.email)
    cliente = Cliente(**dados.model_dump(), situacao=SituacaoCliente.ATIVO)
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


def bloquear_por_saldo_negativo(cliente: Cliente) -> int:
    """Regra 6: bloqueia o cliente e todos os seus cartoes. Retorna nº de cartoes bloqueados."""
    cliente.situacao = SituacaoCliente.BLOQUEADO
    bloqueados = 0
    for conta in cliente.contas:
        for cartao in conta.cartoes:
            if cartao.estado == EstadoCartao.ATIVO:
                cartao.estado = EstadoCartao.BLOQUEADO
                cartao.motivo_bloqueio = MotivoBloqueioCartao.SALDO_NEGATIVO
                bloqueados += 1
    return bloqueados


def atualizar(db: Session, cliente: Cliente, dados: ClienteAtualizar, agora: datetime) -> Cliente:
    campos = dados.model_dump(exclude_unset=True)
    if campos.get("email"):
        _garantir_unicidade(db, None, campos["email"], ignorar_id=cliente.id)
    for campo in ("nome", "email", "categoria"):
        if campos.get(campo) is not None:
            setattr(cliente, campo, campos[campo])

    nova = campos.get("situacao")
    if nova == SituacaoCliente.ATIVO and cliente.situacao == SituacaoCliente.BLOQUEADO:
        if any(negativo_prolongado(c, agora) for c in cliente.contas):
            raise Conflito(
                "Cliente possui conta com saldo negativo ha mais de 30 dias; "
                "regularize o saldo antes de desbloquear"
            )
        cliente.situacao = SituacaoCliente.ATIVO
        # reativa cartoes bloqueados automaticamente pela regra de saldo negativo
        for conta in cliente.contas:
            if conta.estado != EstadoConta.ATIVA:
                continue
            for cartao in conta.cartoes:
                if (cartao.estado == EstadoCartao.BLOQUEADO
                        and cartao.motivo_bloqueio == MotivoBloqueioCartao.SALDO_NEGATIVO):
                    cartao.estado = EstadoCartao.ATIVO
                    cartao.motivo_bloqueio = None
    elif nova == SituacaoCliente.BLOQUEADO:
        cliente.situacao = SituacaoCliente.BLOQUEADO

    db.commit()
    db.refresh(cliente)
    return cliente


def excluir(db: Session, cliente: Cliente) -> None:
    if cliente.contas:
        raise Conflito("Cliente possui contas vinculadas e nao pode ser excluido")
    db.delete(cliente)
    db.commit()
