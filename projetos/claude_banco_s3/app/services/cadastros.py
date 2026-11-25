"""CRUD de clientes, contas e cartoes com as regras associadas."""
import secrets
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.errors import Conflito, RegraViolada
from app.models import (
    Cartao, Cliente, Conta, EstadoCartao, EstadoConta, EstadoFatura, Fatura, SituacaoCliente,
)
from app.regras import DIAS_ATRASO_BLOQUEIO_CARTAO
from app.services.base import bloquear_cartoes_do_cliente, obter
from app.services.rotinas import (
    FATURAS_EM_ABERTO, MOTIVO_MANUAL, atualizar_faturas_do_cartao, conta_negativa_vencida,
)


# ======================= clientes =======================
def criar_cliente(db: Session, dados) -> Cliente:
    if db.scalar(select(Cliente.id).where(Cliente.cpf == dados.cpf)):
        raise Conflito("cpf_duplicado", "Ja existe cliente com este CPF.")
    cliente = Cliente(**dados.model_dump(), situacao=SituacaoCliente.ATIVO, criado_em=clock.agora())
    db.add(cliente)
    db.commit()
    return cliente


def listar_clientes(db: Session, categoria=None, situacao=None, skip=0, limit=100):
    q = select(Cliente)
    if categoria:
        q = q.where(Cliente.categoria == categoria)
    if situacao:
        q = q.where(Cliente.situacao == situacao)
    return db.scalars(q.order_by(Cliente.id).offset(skip).limit(limit)).all()


def atualizar_cliente(db: Session, cliente_id: int, dados) -> Cliente:
    cliente = obter(db, Cliente, cliente_id, "cliente")
    campos = dados.model_dump(exclude_unset=True)
    for k in ("nome", "email", "categoria"):
        if campos.get(k) is not None:
            setattr(cliente, k, campos[k])
    nova = campos.get("situacao")
    if nova == SituacaoCliente.ATIVO and cliente.situacao == SituacaoCliente.BLOQUEADO:
        momento = clock.agora()
        if any(conta_negativa_vencida(c, momento) for c in cliente.contas):
            raise Conflito("saldo_negativo_prolongado",
                           "Cliente possui conta com saldo negativo ha mais de 30 dias; regularize antes.")
        cliente.situacao = SituacaoCliente.ATIVO
    elif nova == SituacaoCliente.BLOQUEADO and cliente.situacao == SituacaoCliente.ATIVO:
        cliente.situacao = SituacaoCliente.BLOQUEADO
        bloquear_cartoes_do_cliente(cliente, MOTIVO_MANUAL)
    db.commit()
    return cliente


def remover_cliente(db: Session, cliente_id: int) -> None:
    cliente = obter(db, Cliente, cliente_id, "cliente")
    if cliente.contas:
        raise Conflito("cliente_com_contas", "Cliente possui contas vinculadas e nao pode ser removido.")
    db.delete(cliente)
    db.commit()


# ======================= contas =======================
def _gerar_numero_conta(db: Session) -> str:
    while True:
        base = f"{secrets.randbelow(10**8):08d}"
        dv = sum(int(d) * (i + 2) for i, d in enumerate(reversed(base))) % 11 % 10
        numero = f"{base}-{dv}"
        if not db.scalar(select(Conta.id).where(Conta.numero == numero)):
            return numero


def criar_conta(db: Session, dados) -> Conta:
    cliente = obter(db, Cliente, dados.cliente_id, "cliente")
    if cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("cliente_bloqueado", "Nao e possivel abrir conta para cliente bloqueado.")
    conta = Conta(
        numero=_gerar_numero_conta(db), cliente_id=cliente.id, tipo=dados.tipo, saldo=Decimal("0.00"),
        limite_credito=dados.limite_credito, estado=EstadoConta.ATIVA, criado_em=clock.agora(),
    )
    db.add(conta)
    db.commit()
    return conta


def listar_contas(db: Session, cliente_id=None, estado=None, skip=0, limit=100):
    q = select(Conta)
    if cliente_id:
        q = q.where(Conta.cliente_id == cliente_id)
    if estado:
        q = q.where(Conta.estado == estado)
    return db.scalars(q.order_by(Conta.id).offset(skip).limit(limit)).all()


def atualizar_conta(db: Session, conta_id: int, dados) -> Conta:
    conta = obter(db, Conta, conta_id, "conta")
    if conta.estado == EstadoConta.ENCERRADA:
        raise Conflito("conta_encerrada", "Conta encerrada nao pode ser alterada.")
    campos = dados.model_dump(exclude_unset=True)
    if campos.get("limite_credito") is not None:
        novo = campos["limite_credito"]
        if conta.saldo < -novo:
            raise RegraViolada("limite_incompativel",
                               f"Saldo atual ({conta.saldo}) excede o novo limite de credito ({novo}).")
        conta.limite_credito = novo
    if campos.get("estado") is not None:
        conta.estado = EstadoConta(campos["estado"])
    db.commit()
    return conta


def encerrar_conta(db: Session, conta_id: int) -> Conta:
    """Regra 7."""
    conta = obter(db, Conta, conta_id, "conta")
    if conta.estado == EstadoConta.ENCERRADA:
        raise Conflito("conta_encerrada", "Conta ja esta encerrada.")
    if conta.saldo != 0:
        raise Conflito("saldo_nao_zerado", f"Encerramento exige saldo zero (saldo atual: {conta.saldo}).")
    momento = clock.agora()
    for cartao in conta.cartoes:
        atualizar_faturas_do_cartao(cartao, momento.date())
    em_aberto = db.scalar(
        select(func.count(Fatura.id)).join(Cartao).where(
            Cartao.conta_id == conta.id, Fatura.estado.in_(FATURAS_EM_ABERTO))
    )
    if em_aberto:
        db.commit()  # persiste eventual atualizacao de atraso
        raise Conflito("faturas_em_aberto", f"Conta possui {em_aberto} fatura(s) nao paga(s).")
    for cartao in conta.cartoes:
        if cartao.estado != EstadoCartao.CANCELADO:
            cartao.estado = EstadoCartao.CANCELADO
            cartao.motivo_bloqueio = None
    conta.estado = EstadoConta.ENCERRADA
    conta.encerrado_em = momento
    db.commit()
    return conta


# ======================= cartoes =======================
def _gerar_numero_cartao(db: Session) -> str:
    while True:
        corpo = "5" + "".join(str(secrets.randbelow(10)) for _ in range(14))
        soma = 0
        for i, d in enumerate(reversed(corpo)):  # digito verificador de Luhn
            n = int(d)
            if i % 2 == 0:
                n *= 2
                n -= 9 if n > 9 else 0
            soma += n
        numero = corpo + str((10 - soma % 10) % 10)
        if not db.scalar(select(Cartao.id).where(Cartao.numero == numero)):
            return numero


def criar_cartao(db: Session, dados) -> Cartao:
    conta = obter(db, Conta, dados.conta_id, "conta")
    if conta.estado != EstadoConta.ATIVA:
        raise Conflito("conta_nao_ativa", f"Conta {conta.numero} esta {conta.estado.value}.")
    if conta.cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("cliente_bloqueado", "Cliente bloqueado nao pode receber cartao.")
    cartao = Cartao(conta_id=conta.id, numero=_gerar_numero_cartao(db), limite=dados.limite,
                    estado=EstadoCartao.ATIVO, criado_em=clock.agora())
    db.add(cartao)
    db.commit()
    return cartao


def listar_cartoes(db: Session, conta_id=None, estado=None, skip=0, limit=100):
    q = select(Cartao)
    if conta_id:
        q = q.where(Cartao.conta_id == conta_id)
    if estado:
        q = q.where(Cartao.estado == estado)
    return db.scalars(q.order_by(Cartao.id).offset(skip).limit(limit)).all()


def atualizar_cartao(db: Session, cartao_id: int, dados) -> Cartao:
    cartao = obter(db, Cartao, cartao_id, "cartao")
    if cartao.estado == EstadoCartao.CANCELADO:
        raise Conflito("cartao_cancelado", "Cartao cancelado nao pode ser alterado.")
    campos = dados.model_dump(exclude_unset=True)
    if campos.get("limite") is not None:
        cartao.limite = campos["limite"]
    novo = campos.get("estado")
    if novo == "bloqueado" and cartao.estado == EstadoCartao.ATIVO:
        cartao.estado = EstadoCartao.BLOQUEADO
        cartao.motivo_bloqueio = MOTIVO_MANUAL
    elif novo == "ativo" and cartao.estado == EstadoCartao.BLOQUEADO:
        hoje = clock.agora().date()
        atualizar_faturas_do_cartao(cartao, hoje)
        if cartao.conta.cliente.situacao != SituacaoCliente.ATIVO:
            db.commit()
            raise Conflito("cliente_bloqueado", "Cliente bloqueado: cartao nao pode ser reativado.")
        if cartao.conta.estado != EstadoConta.ATIVA:
            db.commit()
            raise Conflito("conta_nao_ativa", "Conta do cartao nao esta ativa.")
        if any(f.estado == EstadoFatura.ATRASADA and (hoje - f.data_vencimento).days > DIAS_ATRASO_BLOQUEIO_CARTAO
               for f in cartao.faturas):
            db.commit()
            raise Conflito("fatura_atrasada",
                           f"Cartao possui fatura com mais de {DIAS_ATRASO_BLOQUEIO_CARTAO} dias de atraso.")
        cartao.estado = EstadoCartao.ATIVO
        cartao.motivo_bloqueio = None
    db.commit()
    return cartao


def cancelar_cartao(db: Session, cartao_id: int) -> Cartao:
    cartao = obter(db, Cartao, cartao_id, "cartao")
    if cartao.estado == EstadoCartao.CANCELADO:
        raise Conflito("cartao_cancelado", "Cartao ja esta cancelado.")
    cartao.estado = EstadoCartao.CANCELADO
    cartao.motivo_bloqueio = None
    db.commit()
    return cartao
