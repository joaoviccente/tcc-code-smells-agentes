"""Faturas de cartao: compras, fechamento, atraso, juros e pagamento (regra 5)."""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..config import DIA_VENCIMENTO_FATURA, DIAS_ATRASO_BLOQUEIO_CARTAO, DIAS_BASE_JUROS
from ..enums import EstadoCartao, EstadoConta, EstadoFatura, MotivoBloqueioCartao, SituacaoCliente
from ..errors import Conflito, RegraViolada
from ..models import CENTAVO, Cartao, Fatura
from .comum import ZERO, brl, competencia, obter_cartao, obter_fatura, regras_do_cliente

# Eventos devolvidos por atualizar_situacao_fatura (usados pela rotina diaria)
EVT_FECHADA = "fechada"
EVT_ATRASADA = "atrasada"
EVT_CARTAO_BLOQUEADO = "cartao_bloqueado"


def vencimento_de(mes_referencia: str) -> date:
    ano, mes = map(int, mes_referencia.split("-"))
    ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return date(ano, mes, DIA_VENCIMENTO_FATURA)


def dias_atraso(fatura: Fatura, hoje: date) -> int:
    return max(0, (hoje - fatura.vencimento).days)


def calcular_juros(fatura: Fatura, hoje: date) -> Decimal:
    """Juros simples pro rata die sobre o valor da fatura: valor * taxa_mensal * dias / 30."""
    taxa = regras_do_cliente(fatura.cartao.conta.cliente).juros_atraso_mensal
    dias = dias_atraso(fatura, hoje)
    return (fatura.valor * taxa * Decimal(dias) / Decimal(DIAS_BASE_JUROS)).quantize(CENTAVO, ROUND_HALF_UP)


def atualizar_situacao_fatura(fatura: Fatura, hoje: date) -> set[str]:
    """Aplica as transicoes temporais da fatura. Idempotente para a mesma data."""
    eventos: set[str] = set()
    if fatura.estado == EstadoFatura.ABERTA and fatura.mes_referencia < competencia(hoje):
        if fatura.valor == ZERO:
            fatura.estado = EstadoFatura.PAGA
            fatura.valor_pago = ZERO
        else:
            fatura.estado = EstadoFatura.FECHADA
            eventos.add(EVT_FECHADA)

    if fatura.estado in (EstadoFatura.FECHADA, EstadoFatura.ATRASADA) and hoje > fatura.vencimento:
        if fatura.estado == EstadoFatura.FECHADA:
            eventos.add(EVT_ATRASADA)
        fatura.estado = EstadoFatura.ATRASADA
        fatura.juros = calcular_juros(fatura, hoje)
        cartao = fatura.cartao
        if dias_atraso(fatura, hoje) > DIAS_ATRASO_BLOQUEIO_CARTAO and cartao.estado == EstadoCartao.ATIVO:
            cartao.estado = EstadoCartao.BLOQUEADO
            cartao.motivo_bloqueio = MotivoBloqueioCartao.FATURA_ATRASADA
            eventos.add(EVT_CARTAO_BLOQUEADO)
    return eventos


def possui_atraso_bloqueante(cartao: Cartao, hoje: date) -> bool:
    return any(
        f.estado == EstadoFatura.ATRASADA and dias_atraso(f, hoje) > DIAS_ATRASO_BLOQUEIO_CARTAO
        for f in cartao.faturas
    )


def compromisso_do_cartao(db: Session, cartao: Cartao) -> Decimal:
    """Valor do limite do cartao ja comprometido (faturas nao pagas)."""
    return sum((f.valor_total for f in cartao.faturas if f.estado != EstadoFatura.PAGA), ZERO)


def registrar_compra(db: Session, cartao_id: int, valor: Decimal) -> Fatura:
    cartao = obter_cartao(db, cartao_id)
    hoje = clock.agora().date()
    for f in cartao.faturas:
        atualizar_situacao_fatura(f, hoje)
    db.flush()
    if cartao.estado != EstadoCartao.ATIVO:
        db.commit()
        raise Conflito(f"Cartao {cartao.estado.value}: compra nao permitida")
    if cartao.conta.estado != EstadoConta.ATIVA:
        raise Conflito("Conta do cartao nao esta ativa")
    if cartao.conta.cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("Cliente bloqueado: compra nao permitida")
    disponivel = cartao.limite - compromisso_do_cartao(db, cartao)
    if valor > disponivel:
        raise RegraViolada(f"Limite do cartao insuficiente: disponivel {brl(disponivel)}")

    mes = competencia(hoje)
    fatura = db.scalar(select(Fatura).where(Fatura.cartao_id == cartao.id, Fatura.mes_referencia == mes))
    if fatura is None:
        fatura = Fatura(
            cartao=cartao,
            mes_referencia=mes,
            valor=ZERO,
            juros=ZERO,
            vencimento=vencimento_de(mes),
            estado=EstadoFatura.ABERTA,
        )
        db.add(fatura)
    elif fatura.estado != EstadoFatura.ABERTA:
        raise Conflito(f"Fatura de {mes} nao esta aberta")
    fatura.valor = fatura.valor + valor
    db.commit()
    return fatura


def pagar_fatura(db: Session, fatura_id: int, valor: Decimal) -> Fatura:
    fatura = obter_fatura(db, fatura_id)
    agora = clock.agora()
    hoje = agora.date()
    atualizar_situacao_fatura(fatura, hoje)
    db.flush()
    if fatura.estado == EstadoFatura.PAGA:
        db.commit()
        raise Conflito("Fatura ja esta paga")
    if fatura.estado == EstadoFatura.ABERTA:
        db.commit()
        raise Conflito("Fatura ainda aberta (mes de referencia em curso); aguarde o fechamento")
    devido = fatura.valor_total
    if valor != devido:
        db.commit()
        raise RegraViolada(
            f"Valor do pagamento ({brl(valor)}) difere do valor devido ({brl(devido)}"
            + (f", incluindo juros de {brl(fatura.juros)}" if fatura.juros > 0 else "")
            + ")"
        )
    fatura.estado = EstadoFatura.PAGA
    fatura.valor_pago = valor
    fatura.data_pagamento = agora

    # Desbloqueia o cartao se o bloqueio decorreu do atraso e nao ha outro atraso bloqueante
    cartao = fatura.cartao
    if (
        cartao.estado == EstadoCartao.BLOQUEADO
        and cartao.motivo_bloqueio == MotivoBloqueioCartao.FATURA_ATRASADA
        and not possui_atraso_bloqueante(cartao, hoje)
        and cartao.conta.cliente.situacao == SituacaoCliente.ATIVO
        and cartao.conta.estado == EstadoConta.ATIVA
    ):
        cartao.estado = EstadoCartao.ATIVO
        cartao.motivo_bloqueio = None
    db.commit()
    return fatura
