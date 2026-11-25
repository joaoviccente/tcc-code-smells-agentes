from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import Conflito, RegraViolada
from app.models import (
    Cartao, EstadoCartao, EstadoConta, EstadoFatura, Fatura, MotivoBloqueioCartao,
    SituacaoCliente, arredondar,
)
from app.regras import DIAS_ATRASO_BLOQUEIO_CARTAO, REGRAS
from app.schemas import FaturaCriar
from app.services.cartoes import possui_atraso_bloqueante
from app.services.comum import competencia_de


def vencimento_padrao(mes_referencia: str) -> date:
    ano, mes = map(int, mes_referencia.split("-"))
    ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return date(ano, mes, 10)


def calcular_juros(valor: Decimal, taxa_mensal: Decimal, dias_atraso: int) -> Decimal:
    """Juros simples pro rata die: valor x taxa mensal x dias / 30."""
    if dias_atraso <= 0:
        return Decimal("0.00")
    return arredondar(valor * taxa_mensal * dias_atraso / 30)


def atualizar_situacao(fatura: Fatura, agora: datetime) -> None:
    """Regra 5: fecha a fatura apos o mes de referencia; apos o vencimento passa a
    'atrasada', acumulando juros da categoria; com mais de 10 dias de atraso o
    cartao e bloqueado."""
    if fatura.estado == EstadoFatura.PAGA:
        return
    hoje = agora.date()
    if fatura.estado == EstadoFatura.ABERTA and fatura.mes_referencia < competencia_de(agora):
        fatura.estado = EstadoFatura.FECHADA
    if fatura.estado in (EstadoFatura.ABERTA, EstadoFatura.FECHADA) and hoje > fatura.data_vencimento:
        fatura.estado = EstadoFatura.ATRASADA
    if fatura.estado != EstadoFatura.ATRASADA:
        return

    dias = (hoje - fatura.data_vencimento).days
    categoria = fatura.cartao.conta.cliente.categoria
    fatura.juros = calcular_juros(fatura.valor, REGRAS[categoria].juros_atraso_mensal, dias)

    cartao = fatura.cartao
    if dias > DIAS_ATRASO_BLOQUEIO_CARTAO and cartao.estado == EstadoCartao.ATIVO:
        cartao.estado = EstadoCartao.BLOQUEADO
        cartao.motivo_bloqueio = MotivoBloqueioCartao.ATRASO_FATURA


def listar_por_cartao(db: Session, cartao: Cartao, agora: datetime) -> list[Fatura]:
    faturas = list(
        db.scalars(
            select(Fatura).where(Fatura.cartao_id == cartao.id).order_by(Fatura.mes_referencia)
        )
    )
    for f in faturas:
        atualizar_situacao(f, agora)
    db.commit()
    return faturas


def criar(db: Session, cartao: Cartao, dados: FaturaCriar, agora: datetime) -> Fatura:
    if cartao.estado == EstadoCartao.CANCELADO:
        raise Conflito("Cartao cancelado nao pode receber faturas")
    if dados.valor > cartao.limite:
        raise RegraViolada(f"Valor da fatura excede o limite do cartao ({cartao.limite})")
    vencimento = dados.data_vencimento or vencimento_padrao(dados.mes_referencia)
    if vencimento < vencimento_padrao(dados.mes_referencia).replace(day=1):
        raise RegraViolada("Vencimento deve ser posterior ao mes de referencia")
    fatura = Fatura(
        cartao_id=cartao.id, mes_referencia=dados.mes_referencia, valor=dados.valor,
        juros=Decimal("0.00"), data_vencimento=vencimento, estado=EstadoFatura.ABERTA,
    )
    db.add(fatura)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflito("Ja existe fatura deste cartao para o mes de referencia informado")
    atualizar_situacao(fatura, agora)
    db.commit()
    db.refresh(fatura)
    return fatura


def pagar(db: Session, fatura: Fatura, valor: Decimal, agora: datetime) -> Fatura:
    atualizar_situacao(fatura, agora)
    if fatura.estado == EstadoFatura.PAGA:
        raise Conflito("Fatura ja paga")
    if valor != fatura.valor_total:
        db.commit()  # persiste juros/estado atualizados
        raise RegraViolada(
            f"Valor do pagamento deve ser igual ao total devido: {fatura.valor_total}"
        )
    fatura.estado = EstadoFatura.PAGA
    fatura.valor_pago = valor
    fatura.data_pagamento = agora

    cartao = fatura.cartao
    if (cartao.estado == EstadoCartao.BLOQUEADO
            and cartao.motivo_bloqueio == MotivoBloqueioCartao.ATRASO_FATURA
            and not possui_atraso_bloqueante(cartao)
            and cartao.conta.estado == EstadoConta.ATIVA
            and cartao.conta.cliente.situacao == SituacaoCliente.ATIVO):
        cartao.estado = EstadoCartao.ATIVO
        cartao.motivo_bloqueio = None

    db.commit()
    db.refresh(fatura)
    return fatura
