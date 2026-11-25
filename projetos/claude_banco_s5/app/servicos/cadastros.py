"""CRUD de clientes, contas e cartoes."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock, regras
from app.enums import (
    CategoriaCliente, EstadoCartao, EstadoConta, EstadoFatura, SituacaoCliente, TipoConta,
)
from app.erros import Conflito, RegraNegocio
from app.models import Cartao, Cliente, Conta, Fatura
from app.schemas import (
    CartaoAtualizar, CartaoCriar, ClienteAtualizar, ClienteCriar, ContaAtualizar, ContaCriar,
)
from app.servicos.comum import (
    ZERO, excede_prazo_negativo, gerar_numero_cartao, gerar_numero_conta, obter_cartao,
    obter_cliente, obter_conta,
)

FATURAS_NAO_QUITADAS = (EstadoFatura.ABERTA, EstadoFatura.FECHADA, EstadoFatura.ATRASADA)


# ------------------------------------------------------------------ clientes

def _checar_unicidade_cliente(db: Session, cpf: Optional[str], email: Optional[str],
                              ignorar_id: Optional[int] = None) -> None:
    if cpf is not None:
        q = select(Cliente.id).where(Cliente.cpf == cpf)
        if ignorar_id:
            q = q.where(Cliente.id != ignorar_id)
        if db.scalar(q) is not None:
            raise Conflito("Ja existe cliente com este CPF")
    if email is not None:
        q = select(Cliente.id).where(Cliente.email == email)
        if ignorar_id:
            q = q.where(Cliente.id != ignorar_id)
        if db.scalar(q) is not None:
            raise Conflito("Ja existe cliente com este e-mail")


def criar_cliente(db: Session, dados: ClienteCriar) -> Cliente:
    _checar_unicidade_cliente(db, dados.cpf, dados.email)
    cliente = Cliente(**dados.model_dump(), criado_em=clock.agora())
    db.add(cliente)
    db.commit()
    return cliente


def listar_clientes(db: Session, categoria: Optional[CategoriaCliente],
                    situacao: Optional[SituacaoCliente], cpf: Optional[str],
                    offset: int, limit: int) -> list[Cliente]:
    q = select(Cliente).order_by(Cliente.id)
    if categoria:
        q = q.where(Cliente.categoria == categoria)
    if situacao:
        q = q.where(Cliente.situacao == situacao)
    if cpf:
        q = q.where(Cliente.cpf == cpf)
    return list(db.scalars(q.offset(offset).limit(limit)))


def atualizar_cliente(db: Session, cliente_id: int, dados: ClienteAtualizar) -> Cliente:
    cliente = obter_cliente(db, cliente_id)
    campos = dados.model_dump(exclude_unset=True)
    for nome in ("nome", "email", "categoria", "situacao"):
        if nome in campos and campos[nome] is None:
            raise RegraNegocio(f"Campo '{nome}' nao pode ser nulo")
    _checar_unicidade_cliente(db, None, campos.get("email"), ignorar_id=cliente.id)

    if campos.get("situacao") == SituacaoCliente.ATIVO and cliente.situacao != SituacaoCliente.ATIVO:
        hoje = clock.agora().date()
        if any(excede_prazo_negativo(c, hoje) for c in cliente.contas
               if c.estado != EstadoConta.ENCERRADA):
            raise Conflito("Cliente possui conta com saldo negativo ha mais de "
                           f"{regras.DIAS_SALDO_NEGATIVO_BLOQUEIO} dias; regularize antes de desbloquear")
    for k, v in campos.items():
        setattr(cliente, k, v)
    db.commit()
    return cliente


def remover_cliente(db: Session, cliente_id: int) -> None:
    cliente = obter_cliente(db, cliente_id)
    if cliente.contas:
        raise Conflito("Cliente possui contas vinculadas e nao pode ser removido "
                       "(o historico deve ser preservado)")
    db.delete(cliente)
    db.commit()


# -------------------------------------------------------------------- contas

def criar_conta(db: Session, dados: ContaCriar) -> Conta:
    cliente = obter_cliente(db, dados.cliente_id)
    if cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("Nao e possivel abrir conta para cliente bloqueado")
    if dados.tipo == TipoConta.POUPANCA and dados.limite_credito > 0:
        raise RegraNegocio("Conta poupanca nao admite limite de credito")
    conta = Conta(
        numero=gerar_numero_conta(db), cliente_id=cliente.id, tipo=dados.tipo,
        saldo=ZERO, limite_credito=dados.limite_credito, estado=EstadoConta.ATIVA,
        criada_em=clock.agora(),
    )
    db.add(conta)
    db.commit()
    return conta


def listar_contas(db: Session, cliente_id: Optional[int], estado: Optional[EstadoConta],
                  offset: int, limit: int) -> list[Conta]:
    q = select(Conta).order_by(Conta.id)
    if cliente_id:
        q = q.where(Conta.cliente_id == cliente_id)
    if estado:
        q = q.where(Conta.estado == estado)
    return list(db.scalars(q.offset(offset).limit(limit)))


def atualizar_conta(db: Session, conta_id: int, dados: ContaAtualizar) -> Conta:
    conta = obter_conta(db, conta_id, bloquear=True)
    campos = dados.model_dump(exclude_unset=True)
    if conta.estado == EstadoConta.ENCERRADA:
        raise Conflito("Conta encerrada nao pode ser alterada")
    for nome in ("limite_credito", "estado"):
        if nome in campos and campos[nome] is None:
            raise RegraNegocio(f"Campo '{nome}' nao pode ser nulo")
    if "limite_credito" in campos:
        if conta.tipo == TipoConta.POUPANCA and campos["limite_credito"] > 0:
            raise RegraNegocio("Conta poupanca nao admite limite de credito")
        conta.limite_credito = campos["limite_credito"]
    if "estado" in campos:
        conta.estado = EstadoConta(campos["estado"])
    db.commit()
    return conta


def encerrar_conta(db: Session, conta_id: int) -> Conta:
    """Regra 7: exige saldo zero e nenhuma fatura em aberto; cancela os cartoes."""
    conta = obter_conta(db, conta_id, bloquear=True)
    if conta.estado == EstadoConta.ENCERRADA:
        raise Conflito("Conta ja esta encerrada")
    if conta.saldo != 0:
        raise Conflito(f"Encerramento exige saldo zero (saldo atual: {conta.saldo})")
    pendentes = db.scalar(
        select(Fatura.id).join(Cartao).where(
            Cartao.conta_id == conta.id, Fatura.estado.in_(FATURAS_NAO_QUITADAS)).limit(1))
    if pendentes is not None:
        raise Conflito("Encerramento exige que nao haja faturas em aberto nos cartoes da conta")
    for cartao in conta.cartoes:
        cartao.estado = EstadoCartao.CANCELADO
    conta.estado = EstadoConta.ENCERRADA
    conta.encerrada_em = clock.agora()
    db.commit()
    return conta


# ------------------------------------------------------------------- cartoes

def criar_cartao(db: Session, dados: CartaoCriar) -> Cartao:
    conta = obter_conta(db, dados.conta_id)
    if conta.estado != EstadoConta.ATIVA:
        raise Conflito("Cartao so pode ser emitido para conta ativa")
    if conta.cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("Cartao nao pode ser emitido para cliente bloqueado")
    cartao = Cartao(numero=gerar_numero_cartao(db), conta_id=conta.id, limite=dados.limite,
                    estado=EstadoCartao.ATIVO, criado_em=clock.agora())
    db.add(cartao)
    db.commit()
    return cartao


def listar_cartoes(db: Session, conta_id: Optional[int], estado: Optional[EstadoCartao],
                   offset: int, limit: int) -> list[Cartao]:
    q = select(Cartao).order_by(Cartao.id)
    if conta_id:
        q = q.where(Cartao.conta_id == conta_id)
    if estado:
        q = q.where(Cartao.estado == estado)
    return list(db.scalars(q.offset(offset).limit(limit)))


def atualizar_cartao(db: Session, cartao_id: int, dados: CartaoAtualizar) -> Cartao:
    from app.servicos.faturas import atualizar_faturas_do_cartao

    cartao = obter_cartao(db, cartao_id)
    campos = dados.model_dump(exclude_unset=True)
    if cartao.estado == EstadoCartao.CANCELADO:
        raise Conflito("Cartao cancelado nao pode ser alterado")
    for nome in ("limite", "estado"):
        if nome in campos and campos[nome] is None:
            raise RegraNegocio(f"Campo '{nome}' nao pode ser nulo")
    if campos.get("estado") == EstadoCartao.ATIVO.value and cartao.estado != EstadoCartao.ATIVO:
        atualizar_faturas_do_cartao(db, cartao, clock.agora().date())
        if cartao.conta.estado != EstadoConta.ATIVA:
            raise Conflito("Cartao nao pode ser ativado: conta nao esta ativa")
        if cartao.conta.cliente.situacao != SituacaoCliente.ATIVO:
            raise Conflito("Cartao nao pode ser ativado: cliente bloqueado")
        if any(f.estado == EstadoFatura.ATRASADA for f in cartao.faturas):
            raise Conflito("Cartao nao pode ser ativado: possui fatura em atraso")
    for k, v in campos.items():
        setattr(cartao, k, EstadoCartao(v) if k == "estado" else v)
    db.commit()
    return cartao


def cancelar_cartao(db: Session, cartao_id: int) -> Cartao:
    cartao = obter_cartao(db, cartao_id)
    if cartao.estado == EstadoCartao.CANCELADO:
        raise Conflito("Cartao ja esta cancelado")
    cartao.estado = EstadoCartao.CANCELADO
    db.commit()
    return cartao
