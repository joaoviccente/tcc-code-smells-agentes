"""CRUD de clientes, contas e cartoes."""
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..enums import (
    EstadoCartao,
    EstadoConta,
    EstadoFatura,
    MotivoBloqueioCartao,
    SituacaoCliente,
    TipoConta,
)
from ..errors import Conflito, RegraViolada
from ..models import Cartao, Cliente, Conta, Fatura
from ..schemas import CartaoCreate, CartaoUpdate, ClienteCreate, ClienteUpdate, ContaCreate, ContaUpdate
from .comum import ZERO, brl, obter_cartao, obter_cliente, obter_conta
from .faturas import atualizar_situacao_fatura, compromisso_do_cartao, possui_atraso_bloqueante


# ======================================================================= Clientes
def _checar_unicidade_cliente(db: Session, cpf: str | None, email: str | None, ignorar_id: int | None = None):
    if cpf:
        existente = db.scalar(select(Cliente).where(Cliente.cpf == cpf))
        if existente and existente.id != ignorar_id:
            raise Conflito("Ja existe cliente com este CPF")
    if email:
        existente = db.scalar(select(Cliente).where(Cliente.email == email))
        if existente and existente.id != ignorar_id:
            raise Conflito("Ja existe cliente com este e-mail")


def criar_cliente(db: Session, dados: ClienteCreate) -> Cliente:
    _checar_unicidade_cliente(db, dados.cpf, dados.email)
    cliente = Cliente(
        nome=dados.nome,
        cpf=dados.cpf,
        email=dados.email,
        categoria=dados.categoria,
        situacao=SituacaoCliente.ATIVO,
        criado_em=clock.agora(),
    )
    db.add(cliente)
    db.commit()
    return cliente


def listar_clientes(db: Session, categoria=None, situacao=None, skip=0, limit=100) -> list[Cliente]:
    q = select(Cliente).order_by(Cliente.id)
    if categoria:
        q = q.where(Cliente.categoria == categoria)
    if situacao:
        q = q.where(Cliente.situacao == situacao)
    return list(db.scalars(q.offset(skip).limit(limit)))


def atualizar_cliente(db: Session, cliente_id: int, dados: ClienteUpdate) -> Cliente:
    cliente = obter_cliente(db, cliente_id)
    campos = dados.model_dump(exclude_unset=True)
    for campo in ("nome", "email", "categoria", "situacao"):
        if campo in campos and campos[campo] is None:
            raise RegraViolada(f"Campo '{campo}' nao pode ser nulo")
    _checar_unicidade_cliente(db, None, campos.get("email"), ignorar_id=cliente.id)
    for campo, valor in campos.items():
        setattr(cliente, campo, valor)
    db.commit()
    return cliente


def remover_cliente(db: Session, cliente_id: int) -> None:
    cliente = obter_cliente(db, cliente_id)
    if cliente.contas:
        raise Conflito("Cliente possui contas vinculadas e nao pode ser removido; bloqueie-o ou encerre as contas")
    db.delete(cliente)
    db.commit()


# ======================================================================= Contas
def _gerar_numero_conta(db: Session) -> str:
    while True:
        base = f"{secrets.randbelow(10**7):07d}"
        dv = sum(int(d) * (i + 2) for i, d in enumerate(reversed(base))) % 11 % 10
        numero = f"{base}-{dv}"
        if not db.scalar(select(Conta.id).where(Conta.numero == numero)):
            return numero


def criar_conta(db: Session, dados: ContaCreate) -> Conta:
    cliente = obter_cliente(db, dados.cliente_id)
    if cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("Cliente bloqueado nao pode abrir novas contas")
    if dados.tipo == TipoConta.POUPANCA and dados.limite_credito > 0:
        raise RegraViolada("Conta poupanca nao admite limite de credito")
    conta = Conta(
        numero=_gerar_numero_conta(db),
        cliente_id=cliente.id,
        tipo=dados.tipo,
        saldo=ZERO,
        limite_credito=dados.limite_credito,
        estado=EstadoConta.ATIVA,
        criado_em=clock.agora(),
    )
    db.add(conta)
    db.commit()
    return conta


def listar_contas(db: Session, cliente_id=None, estado=None, skip=0, limit=100) -> list[Conta]:
    q = select(Conta).order_by(Conta.id)
    if cliente_id:
        q = q.where(Conta.cliente_id == cliente_id)
    if estado:
        q = q.where(Conta.estado == estado)
    return list(db.scalars(q.offset(skip).limit(limit)))


def atualizar_conta(db: Session, conta_id: int, dados: ContaUpdate) -> Conta:
    conta = obter_conta(db, conta_id)
    if conta.estado == EstadoConta.ENCERRADA:
        raise Conflito("Conta encerrada nao pode ser alterada")
    campos = dados.model_dump(exclude_unset=True)
    if "limite_credito" in campos:
        novo = campos["limite_credito"]
        if novo is None:
            raise RegraViolada("Campo 'limite_credito' nao pode ser nulo")
        if conta.tipo == TipoConta.POUPANCA and novo > 0:
            raise RegraViolada("Conta poupanca nao admite limite de credito")
        if conta.saldo < -novo:
            raise RegraViolada(
                f"Novo limite {brl(novo)} e inferior ao saldo devedor atual ({brl(conta.saldo)})"
            )
        conta.limite_credito = novo
    if "estado" in campos:
        estado = campos["estado"]
        if estado is None:
            raise RegraViolada("Campo 'estado' nao pode ser nulo")
        if estado == EstadoConta.ENCERRADA:
            raise Conflito("Use DELETE /contas/{id} para encerrar a conta")
        conta.estado = estado
    db.commit()
    return conta


def encerrar_conta(db: Session, conta_id: int) -> Conta:
    """Regra 7: exige saldo zero e nenhuma fatura em aberto; cancela os cartoes."""
    conta = obter_conta(db, conta_id)
    if conta.estado == EstadoConta.ENCERRADA:
        raise Conflito("Conta ja esta encerrada")
    if conta.saldo != ZERO:
        raise Conflito(f"Conta so pode ser encerrada com saldo zero (saldo atual {brl(conta.saldo)})")
    agora = clock.agora()
    pendentes = []
    for cartao in conta.cartoes:
        for fatura in cartao.faturas:
            atualizar_situacao_fatura(fatura, agora.date())
            if fatura.estado != EstadoFatura.PAGA and fatura.valor_total > 0:
                pendentes.append(fatura)
    if pendentes:
        db.commit()  # persiste eventuais atualizacoes de situacao das faturas
        desc = ", ".join(f"{f.mes_referencia} (cartao {f.cartao_id}, {f.estado.value})" for f in pendentes)
        raise Conflito(f"Conta possui faturas em aberto: {desc}")
    for cartao in conta.cartoes:
        cartao.estado = EstadoCartao.CANCELADO
        for fatura in cartao.faturas:  # faturas zeradas remanescentes
            if fatura.estado != EstadoFatura.PAGA:
                fatura.estado = EstadoFatura.PAGA
                fatura.valor_pago = ZERO
                fatura.data_pagamento = agora
    conta.estado = EstadoConta.ENCERRADA
    conta.encerrada_em = agora
    conta.negativo_desde = None
    db.commit()
    return conta


# ======================================================================= Cartoes
def _gerar_numero_cartao(db: Session) -> str:
    while True:
        parcial = "5" + "".join(str(secrets.randbelow(10)) for _ in range(14))
        soma = 0
        for i, d in enumerate(reversed(parcial)):
            n = int(d)
            if i % 2 == 0:
                n *= 2
                if n > 9:
                    n -= 9
            soma += n
        numero = parcial + str((10 - soma % 10) % 10)  # digito de Luhn
        if not db.scalar(select(Cartao.id).where(Cartao.numero == numero)):
            return numero


def criar_cartao(db: Session, dados: CartaoCreate) -> Cartao:
    conta = obter_conta(db, dados.conta_id)
    if conta.estado != EstadoConta.ATIVA:
        raise Conflito("Cartao so pode ser emitido para conta ativa")
    if conta.cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("Cliente bloqueado nao pode receber novos cartoes")
    cartao = Cartao(
        conta_id=conta.id,
        numero=_gerar_numero_cartao(db),
        limite=dados.limite,
        estado=EstadoCartao.ATIVO,
        criado_em=clock.agora(),
    )
    db.add(cartao)
    db.commit()
    return cartao


def listar_cartoes(db: Session, conta_id=None, estado=None, skip=0, limit=100) -> list[Cartao]:
    q = select(Cartao).order_by(Cartao.id)
    if conta_id:
        q = q.where(Cartao.conta_id == conta_id)
    if estado:
        q = q.where(Cartao.estado == estado)
    return list(db.scalars(q.offset(skip).limit(limit)))


def atualizar_cartao(db: Session, cartao_id: int, dados: CartaoUpdate) -> Cartao:
    cartao = obter_cartao(db, cartao_id)
    if cartao.estado == EstadoCartao.CANCELADO:
        raise Conflito("Cartao cancelado nao pode ser alterado")
    campos = dados.model_dump(exclude_unset=True)
    if "limite" in campos:
        if campos["limite"] is None:
            raise RegraViolada("Campo 'limite' nao pode ser nulo")
        usado = compromisso_do_cartao(db, cartao)
        if campos["limite"] < usado:
            raise RegraViolada(f"Novo limite inferior ao valor ja utilizado no cartao ({brl(usado)})")
        cartao.limite = campos["limite"]
    if "estado" in campos:
        estado = campos["estado"]
        if estado is None:
            raise RegraViolada("Campo 'estado' nao pode ser nulo")
        if estado == EstadoCartao.CANCELADO:
            raise Conflito("Use DELETE /cartoes/{id} para cancelar o cartao")
        if estado == EstadoCartao.ATIVO and cartao.estado != EstadoCartao.ATIVO:
            _validar_desbloqueio(db, cartao)
            cartao.motivo_bloqueio = None
        elif estado == EstadoCartao.BLOQUEADO and cartao.estado != EstadoCartao.BLOQUEADO:
            cartao.motivo_bloqueio = MotivoBloqueioCartao.MANUAL
        cartao.estado = estado
    db.commit()
    return cartao


def _validar_desbloqueio(db: Session, cartao: Cartao) -> None:
    if cartao.conta.estado != EstadoConta.ATIVA:
        raise Conflito("Conta do cartao nao esta ativa")
    if cartao.conta.cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("Cliente bloqueado: cartao nao pode ser desbloqueado")
    hoje = clock.agora().date()
    for f in cartao.faturas:
        atualizar_situacao_fatura(f, hoje)
    if possui_atraso_bloqueante(cartao, hoje):
        raise Conflito("Cartao possui fatura com mais de 10 dias de atraso")


def cancelar_cartao(db: Session, cartao_id: int) -> Cartao:
    cartao = obter_cartao(db, cartao_id)
    if cartao.estado == EstadoCartao.CANCELADO:
        raise Conflito("Cartao ja esta cancelado")
    cartao.estado = EstadoCartao.CANCELADO
    db.commit()
    return cartao


def faturas_do_cartao(db: Session, cartao_id: int, estado=None) -> list[Fatura]:
    cartao = obter_cartao(db, cartao_id)
    hoje = clock.agora().date()
    for f in cartao.faturas:
        atualizar_situacao_fatura(f, hoje)
    db.commit()
    q = select(Fatura).where(Fatura.cartao_id == cartao.id).order_by(Fatura.mes_referencia)
    if estado:
        q = q.where(Fatura.estado == estado)
    return list(db.scalars(q))
