"""Faturas de cartao (regra 5)."""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock, regras
from app.enums import EstadoCartao, EstadoFatura
from app.erros import Conflito, NaoEncontrado, RegraNegocio
from app.models import CENTAVO, Cartao, Fatura
from app.schemas import FaturaCriar
from app.servicos.comum import obter_cartao, proximo_mes

EM_ABERTO = (EstadoFatura.ABERTA, EstadoFatura.FECHADA, EstadoFatura.ATRASADA)


def calcular_juros(valor: Decimal, taxa_mensal: Decimal, dias_atraso: int) -> Decimal:
    """Juros simples pro rata die: valor x taxa mensal x dias/30."""
    if dias_atraso <= 0:
        return Decimal("0.00")
    return (valor * taxa_mensal * Decimal(dias_atraso) / Decimal(30)).quantize(
        CENTAVO, rounding=ROUND_HALF_UP)


def atualizar_fatura(fatura: Fatura, hoje: date) -> dict:
    """Aplica a regra 5 a uma fatura (idempotente para a mesma data)."""
    r = {"atrasada": False, "juros": False, "cartao_bloqueado": False}
    if fatura.estado not in EM_ABERTO or hoje <= fatura.data_vencimento:
        return r
    if fatura.estado != EstadoFatura.ATRASADA:
        fatura.estado = EstadoFatura.ATRASADA
        r["atrasada"] = True
    cartao = fatura.cartao
    categoria = cartao.conta.cliente.categoria
    dias = (hoje - fatura.data_vencimento).days
    juros = calcular_juros(fatura.valor, regras.regra(categoria).juros_atraso_mensal, dias)
    if juros != fatura.juros:
        fatura.juros = juros
        r["juros"] = True
    if dias > regras.DIAS_ATRASO_BLOQUEIO_CARTAO and cartao.estado == EstadoCartao.ATIVO:
        cartao.estado = EstadoCartao.BLOQUEADO
        r["cartao_bloqueado"] = True
    return r


def atualizar_faturas_do_cartao(db: Session, cartao: Cartao, hoje: date) -> None:
    for f in cartao.faturas:
        atualizar_fatura(f, hoje)


def obter_fatura(db: Session, fatura_id: int) -> Fatura:
    f = db.get(Fatura, fatura_id)
    if f is None:
        raise NaoEncontrado(f"Fatura {fatura_id} nao encontrada")
    return f


def vencimento_padrao(mes: str) -> date:
    ano, m = (int(x) for x in mes.split("-"))
    a, mm = proximo_mes(ano, m)
    return date(a, mm, regras.DIA_VENCIMENTO_PADRAO)


def criar_fatura(db: Session, cartao_id: int, dados: FaturaCriar) -> Fatura:
    cartao = obter_cartao(db, cartao_id)
    if cartao.estado == EstadoCartao.CANCELADO:
        raise Conflito("Cartao cancelado nao pode receber faturas")
    if dados.valor > cartao.limite:
        raise RegraNegocio(f"Valor da fatura excede o limite do cartao ({cartao.limite})")
    if db.scalar(select(Fatura.id).where(Fatura.cartao_id == cartao.id,
                                         Fatura.mes_referencia == dados.mes_referencia)):
        raise Conflito(f"Ja existe fatura do cartao para {dados.mes_referencia}")
    venc = dados.data_vencimento or vencimento_padrao(dados.mes_referencia)
    ano, mes = (int(x) for x in dados.mes_referencia.split("-"))
    if venc < date(ano, mes, 1):
        raise RegraNegocio("Data de vencimento anterior ao mes de referencia")
    fatura = Fatura(cartao_id=cartao.id, mes_referencia=dados.mes_referencia, valor=dados.valor,
                    juros=Decimal("0.00"), data_vencimento=venc, estado=EstadoFatura.ABERTA)
    db.add(fatura)
    db.flush()
    atualizar_fatura(fatura, clock.agora().date())
    db.commit()
    return fatura


def listar_faturas(db: Session, cartao_id: int, estado: Optional[EstadoFatura]) -> list[Fatura]:
    cartao = obter_cartao(db, cartao_id)
    atualizar_faturas_do_cartao(db, cartao, clock.agora().date())
    db.commit()
    q = select(Fatura).where(Fatura.cartao_id == cartao_id).order_by(Fatura.mes_referencia)
    if estado:
        q = q.where(Fatura.estado == estado)
    return list(db.scalars(q))


def consultar_fatura(db: Session, fatura_id: int) -> Fatura:
    f = obter_fatura(db, fatura_id)
    atualizar_fatura(f, clock.agora().date())
    db.commit()
    return f


def fechar_fatura(db: Session, fatura_id: int) -> Fatura:
    f = obter_fatura(db, fatura_id)
    atualizar_fatura(f, clock.agora().date())
    if f.estado != EstadoFatura.ABERTA:
        db.commit()
        raise Conflito(f"Somente faturas abertas podem ser fechadas (estado: {f.estado.value})")
    f.estado = EstadoFatura.FECHADA
    db.commit()
    return f


def pagar_fatura(db: Session, fatura_id: int, valor: Decimal) -> Fatura:
    agora = clock.agora()
    f = obter_fatura(db, fatura_id)
    atualizar_fatura(f, agora.date())
    db.commit()  # persiste atraso/juros mesmo que o pagamento seja recusado
    if f.estado == EstadoFatura.PAGA:
        raise Conflito("Fatura ja esta paga")
    if valor != f.valor_total:
        raise RegraNegocio(
            f"Valor do pagamento ({valor}) difere do total devido ({f.valor_total} = "
            f"{f.valor} + juros {f.juros})")
    f.estado = EstadoFatura.PAGA
    f.valor_pago = valor
    f.data_pagamento = agora
    db.commit()
    return f
