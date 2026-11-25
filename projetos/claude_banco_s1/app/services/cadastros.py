import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import Conflito, RegraViolada
from app.models import Cartao, Cliente, Conta
from app.services import faturas
from app.services.comum import ZERO, negativo_excedido, obter


def _commit_unico(db: Session, mensagem: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflito(mensagem)


# ---------------- Clientes ----------------
def criar_cliente(db: Session, dados: dict, momento: datetime) -> Cliente:
    if db.scalar(select(Cliente.id).where(Cliente.cpf == dados["cpf"])):
        raise Conflito("CPF ja cadastrado")
    if db.scalar(select(Cliente.id).where(Cliente.email == dados["email"])):
        raise Conflito("E-mail ja cadastrado")
    cliente = Cliente(**dados, situacao="ativo", criado_em=momento)
    db.add(cliente)
    _commit_unico(db, "CPF ou e-mail ja cadastrado")
    return cliente


def atualizar_cliente(db: Session, cliente_id: int, dados: dict, momento: datetime) -> Cliente:
    cliente = obter(db, Cliente, cliente_id, "Cliente")
    if "email" in dados and dados["email"] != cliente.email:
        if db.scalar(select(Cliente.id).where(Cliente.email == dados["email"])):
            raise Conflito("E-mail ja cadastrado")
    if dados.get("situacao") == "ativo" and cliente.situacao == "bloqueado":
        if any(negativo_excedido(c, momento) for c in cliente.contas):
            raise Conflito("Cliente possui conta com saldo negativo ha mais de 30 dias")
    for campo, valor in dados.items():
        setattr(cliente, campo, valor)
    _commit_unico(db, "E-mail ja cadastrado")
    return cliente


def excluir_cliente(db: Session, cliente_id: int) -> None:
    cliente = obter(db, Cliente, cliente_id, "Cliente")
    if cliente.contas:
        raise Conflito("Cliente possui contas vinculadas e nao pode ser excluido")
    db.delete(cliente)
    db.commit()


# ---------------- Contas ----------------
def _numero_conta(db: Session) -> str:
    while True:
        base = f"{secrets.randbelow(10**7):07d}"
        dv = sum(int(d) * (i + 2) for i, d in enumerate(reversed(base))) % 11 % 10
        numero = f"{base}-{dv}"
        if not db.scalar(select(Conta.id).where(Conta.numero == numero)):
            return numero


def criar_conta(db: Session, dados: dict, momento: datetime) -> Conta:
    cliente = obter(db, Cliente, dados["cliente_id"], "Cliente")
    if cliente.situacao != "ativo":
        raise Conflito("Cliente bloqueado nao pode abrir contas")
    conta = Conta(
        numero=_numero_conta(db),
        cliente_id=cliente.id,
        tipo=dados["tipo"],
        saldo=ZERO,
        limite_credito=dados["limite_credito"],
        estado="ativa",
        criada_em=momento,
    )
    db.add(conta)
    _commit_unico(db, "Falha ao gerar numero de conta unico")
    return conta


def atualizar_conta(db: Session, conta_id: int, dados: dict) -> Conta:
    conta = obter(db, Conta, conta_id, "Conta")
    if conta.estado == "encerrada":
        raise Conflito("Conta encerrada nao pode ser alterada")
    novo_limite = dados.get("limite_credito")
    if novo_limite is not None and conta.saldo < -novo_limite:
        raise RegraViolada("Novo limite de credito e inferior ao saldo devedor atual")
    if dados.get("estado") == "ativa" and conta.cliente.situacao != "ativo":
        raise Conflito("Conta de cliente bloqueado nao pode ser reativada")
    for campo, valor in dados.items():
        setattr(conta, campo, valor)
    db.commit()
    return conta


def encerrar_conta(db: Session, conta_id: int, momento: datetime) -> Conta:
    """Regra 7: exige saldo zero e nenhuma fatura em aberto; cancela todos os cartoes."""
    conta = obter(db, Conta, conta_id, "Conta")
    if conta.estado == "encerrada":
        raise Conflito("Conta ja encerrada")
    if conta.saldo != ZERO:
        raise RegraViolada(f"Conta deve ter saldo zero para ser encerrada (saldo atual: {conta.saldo})")
    if faturas.possui_em_aberto(db, conta.id):
        raise Conflito("Conta possui faturas em aberto")
    for cartao in conta.cartoes:
        cartao.estado = "cancelado"
    conta.estado = "encerrada"
    conta.encerrada_em = momento
    db.commit()
    return conta


# ---------------- Cartoes ----------------
def _numero_cartao(db: Session) -> str:
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
        numero = parcial + str((10 - soma % 10) % 10)  # digito verificador de Luhn
        if not db.scalar(select(Cartao.id).where(Cartao.numero == numero)):
            return numero


def criar_cartao(db: Session, dados: dict, momento: datetime) -> Cartao:
    conta = obter(db, Conta, dados["conta_id"], "Conta")
    if conta.estado != "ativa":
        raise Conflito(f"Conta nao esta ativa (estado: {conta.estado})")
    if conta.cliente.situacao != "ativo":
        raise Conflito("Cliente bloqueado nao pode emitir cartoes")
    cartao = Cartao(
        numero=_numero_cartao(db), conta_id=conta.id, limite=dados["limite"], estado="ativo", criado_em=momento
    )
    db.add(cartao)
    _commit_unico(db, "Falha ao gerar numero de cartao unico")
    return cartao


def atualizar_cartao(db: Session, cartao_id: int, dados: dict, momento: datetime) -> Cartao:
    cartao = obter(db, Cartao, cartao_id, "Cartao")
    if cartao.estado == "cancelado":
        raise Conflito("Cartao cancelado nao pode ser alterado")
    if dados.get("estado") == "ativo" and cartao.estado != "ativo":
        if cartao.conta.cliente.situacao != "ativo":
            raise Conflito("Cliente bloqueado: cartao nao pode ser desbloqueado")
        if faturas.possui_atraso_bloqueante(db, cartao, momento):
            db.commit()
            raise Conflito("Cartao possui fatura com mais de 10 dias de atraso")
    for campo, valor in dados.items():
        setattr(cartao, campo, valor)
    db.commit()
    return cartao


def cancelar_cartao(db: Session, cartao_id: int) -> Cartao:
    cartao = obter(db, Cartao, cartao_id, "Cartao")
    if cartao.estado == "cancelado":
        raise Conflito("Cartao ja cancelado")
    cartao.estado = "cancelado"
    db.commit()
    return cartao
