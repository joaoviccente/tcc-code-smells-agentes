from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import PRAZO_ESTORNO_HORAS, regra
from app.errors import Conflito, RegraViolada
from app.models import Conta, Transacao
from app.services import tarifas
from app.services.comum import (
    ZERO,
    exigir_nao_encerrada,
    exigir_operavel,
    fim_do_dia,
    inicio_do_dia,
    movimentar,
    obter,
    pode_debitar,
)


def _nova(db: Session, **campos) -> Transacao:
    t = Transacao(estado="efetivada", **campos)
    db.add(t)
    db.flush()
    return t


def depositar(db: Session, conta_id: int, valor: Decimal, descricao: str | None, momento: datetime):
    conta = obter(db, Conta, conta_id, "Conta")
    exigir_nao_encerrada(conta)
    transacao = _nova(db, conta_id=conta.id, tipo="deposito", valor=valor, data=momento, descricao=descricao)
    movimentar(conta, valor, momento)
    tarifas.cobrar_pendentes(db, conta, momento)
    db.commit()
    return transacao, None, conta


def sacado_no_dia(db: Session, cliente_id: int, momento: datetime) -> Decimal:
    """Total sacado no dia por todas as contas do cliente (saques efetivados, nao estornados)."""
    valores = db.scalars(
        select(Transacao.valor)
        .join(Conta, Conta.id == Transacao.conta_id)
        .where(
            Conta.cliente_id == cliente_id,
            Transacao.tipo == "saque",
            Transacao.estado == "efetivada",
            Transacao.data >= inicio_do_dia(momento),
            Transacao.data < fim_do_dia(momento),
        )
    ).all()
    return sum(valores, ZERO)


def sacar(db: Session, conta_id: int, valor: Decimal, descricao: str | None, momento: datetime):
    conta = obter(db, Conta, conta_id, "Conta")
    exigir_operavel(db, conta, momento)

    limite = regra(conta.cliente.categoria).limite_diario_saque
    ja_sacado = sacado_no_dia(db, conta.cliente_id, momento)
    if ja_sacado + valor > limite:
        raise RegraViolada(
            f"Limite diario de saque da categoria {conta.cliente.categoria} excedido "
            f"(limite {limite}, ja sacado hoje {ja_sacado}, disponivel {max(limite - ja_sacado, ZERO)})"
        )

    tarifa_valor = tarifas.tarifa_devida_por_transacao(db, conta, momento)
    if not pode_debitar(conta, valor + tarifa_valor):
        raise RegraViolada("Saldo insuficiente: operacao excede o limite de credito da conta")

    transacao = _nova(db, conta_id=conta.id, tipo="saque", valor=valor, data=momento, descricao=descricao)
    movimentar(conta, -valor, momento)
    tarifa = tarifas.registrar_tarifa_transacao(db, conta, transacao, tarifa_valor, momento)
    db.commit()
    return transacao, tarifa, conta


def transferir(
    db: Session, origem_id: int, destino_id: int, valor: Decimal, descricao: str | None, momento: datetime
):
    if origem_id == destino_id:
        raise RegraViolada("Conta de origem e destino devem ser diferentes")
    origem = obter(db, Conta, origem_id, "Conta de origem")
    destino = obter(db, Conta, destino_id, "Conta de destino")
    exigir_operavel(db, origem, momento)
    exigir_nao_encerrada(destino)

    limite = regra(origem.cliente.categoria).limite_por_transferencia
    if valor > limite:
        raise RegraViolada(
            f"Valor excede o limite por transferencia da categoria {origem.cliente.categoria} ({limite})"
        )

    mesmo_titular = origem.cliente_id == destino.cliente_id
    tarifa_valor = ZERO if mesmo_titular else tarifas.tarifa_devida_por_transacao(db, origem, momento)
    if not pode_debitar(origem, valor + tarifa_valor):
        raise RegraViolada("Saldo insuficiente: operacao excede o limite de credito da conta")

    transacao = _nova(
        db,
        conta_id=origem.id,
        conta_destino_id=destino.id,
        tipo="transferencia",
        valor=valor,
        data=momento,
        descricao=descricao,
    )
    movimentar(origem, -valor, momento)
    movimentar(destino, valor, momento)
    tarifa = None
    if not mesmo_titular:
        tarifa = tarifas.registrar_tarifa_transacao(db, origem, transacao, tarifa_valor, momento)
    tarifas.cobrar_pendentes(db, destino, momento)
    db.commit()
    return transacao, tarifa, origem


def estornar(db: Session, transacao_id: int, momento: datetime):
    original = obter(db, Transacao, transacao_id, "Transacao")
    if original.tipo == "estorno":
        raise Conflito("Um estorno nao pode ser estornado")
    if original.estado != "efetivada":
        raise Conflito(f"Apenas transacoes efetivadas podem ser estornadas (estado: {original.estado})")
    if momento - original.data > timedelta(hours=PRAZO_ESTORNO_HORAS):
        raise RegraViolada(f"Prazo de estorno de {PRAZO_ESTORNO_HORAS} horas expirado")

    conta = original.conta
    destino = original.conta_destino
    exigir_nao_encerrada(conta)
    if destino is not None:
        exigir_nao_encerrada(destino)

    # Movimentos inversos aos da transacao original: (conta, delta)
    if original.tipo == "deposito":
        movimentos = [(conta, -original.valor)]
    elif original.tipo == "saque":
        movimentos = [(conta, original.valor)]
    else:  # transferencia
        movimentos = [(destino, -original.valor), (conta, original.valor)]

    for c, delta in movimentos:
        if delta < ZERO and not pode_debitar(c, -delta):
            raise RegraViolada(f"Saldo insuficiente na conta {c.id} para reverter a transacao")

    for c, delta in movimentos:
        movimentar(c, delta, momento)
    original.estado = "estornada"
    estorno = _nova(
        db,
        conta_id=original.conta_id,
        conta_destino_id=original.conta_destino_id,
        tipo="estorno",
        valor=original.valor,
        data=momento,
        transacao_original_id=original.id,
        descricao=f"Estorno da transacao {original.id}",
    )
    db.commit()
    return estorno, None, conta


def efeito_na_conta(t: Transacao, conta_id: int) -> Decimal:
    """Efeito (com sinal) de uma transacao sobre o saldo de uma conta."""
    if t.tipo == "deposito":
        return t.valor
    if t.tipo == "saque":
        return -t.valor
    if t.tipo == "transferencia":
        return -t.valor if t.conta_id == conta_id else t.valor
    # estorno: inverso da transacao original
    original = t.transacao_original
    return -efeito_na_conta(original, conta_id)


def extrato(db: Session, conta_id: int, inicio: datetime | None, fim: datetime | None):
    conta = obter(db, Conta, conta_id, "Conta")
    if inicio and fim and inicio > fim:
        raise RegraViolada("Data inicial posterior a data final")
    consulta = select(Transacao).where(or_(Transacao.conta_id == conta.id, Transacao.conta_destino_id == conta.id))
    if inicio:
        consulta = consulta.where(Transacao.data >= inicio)
    if fim:
        consulta = consulta.where(Transacao.data <= fim)
    transacoes = db.scalars(consulta.order_by(Transacao.data, Transacao.id)).all()
    lancamentos = []
    for t in transacoes:
        efeito = efeito_na_conta(t, conta.id)
        lancamentos.append(
            {"transacao": t, "natureza": "credito" if efeito > 0 else "debito", "efeito": efeito}
        )
    return {
        "conta_id": conta.id,
        "numero": conta.numero,
        "saldo_atual": conta.saldo,
        "limite_credito": conta.limite_credito,
        "inicio": inicio,
        "fim": fim,
        "lancamentos": lancamentos,
    }
