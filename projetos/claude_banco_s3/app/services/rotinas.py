"""Regras dependentes do tempo (5 e 6) e tarifa mensal.

Sao avaliadas de forma preguicosa nas operacoes relevantes e tambem por
rotinas batch expostas em /rotinas (para execucao agendada).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Cliente, Conta, EstadoCartao, EstadoConta, EstadoFatura, EstadoTarifa, Fatura,
    SituacaoCliente, Tarifa, TipoTarifa,
)
from app.money import arredondar
from app.regras import (
    DIAS_ATRASO_BLOQUEIO_CARTAO, DIAS_NEGATIVO_BLOQUEIO_CLIENTE, DIAS_POR_MES_JUROS, regra_de,
)
from app.services.base import ajustar_saldo, bloquear_cartoes_do_cliente

MOTIVO_FATURA_ATRASADA = "fatura_atrasada"
MOTIVO_CLIENTE_BLOQUEADO = "cliente_bloqueado"
MOTIVO_MANUAL = "manual"

FATURAS_EM_ABERTO = (EstadoFatura.ABERTA, EstadoFatura.FECHADA, EstadoFatura.ATRASADA)


# ---------- regra 5: faturas em atraso ----------
def atualizar_fatura(fatura: Fatura, hoje: date) -> tuple[bool, bool]:
    """Marca atraso, recalcula juros (simples, pro rata dia) e bloqueia o cartao
    apos 10 dias de atraso. Idempotente. Retorna (ficou_atrasada, cartao_bloqueado)."""
    if fatura.estado not in FATURAS_EM_ABERTO or hoje <= fatura.data_vencimento:
        return False, False
    nova = fatura.estado != EstadoFatura.ATRASADA
    fatura.estado = EstadoFatura.ATRASADA
    dias = (hoje - fatura.data_vencimento).days
    taxa = regra_de(fatura.cartao.conta.cliente.categoria).juros_atraso_mensal
    fatura.juros = arredondar(fatura.valor_original * taxa * Decimal(dias) / DIAS_POR_MES_JUROS)
    fatura.valor = fatura.valor_original + fatura.juros

    bloqueou = False
    cartao = fatura.cartao
    if dias > DIAS_ATRASO_BLOQUEIO_CARTAO and cartao.estado == EstadoCartao.ATIVO:
        cartao.estado = EstadoCartao.BLOQUEADO
        cartao.motivo_bloqueio = MOTIVO_FATURA_ATRASADA
        bloqueou = True
    return nova, bloqueou


def atualizar_faturas_do_cartao(cartao, hoje: date) -> None:
    for f in cartao.faturas:
        atualizar_fatura(f, hoje)


# ---------- regra 6: saldo negativo prolongado ----------
def conta_negativa_vencida(conta: Conta, momento: datetime) -> bool:
    return (
        conta.estado != EstadoConta.ENCERRADA
        and conta.saldo < 0
        and conta.negativo_desde is not None
        and momento - conta.negativo_desde > timedelta(days=DIAS_NEGATIVO_BLOQUEIO_CLIENTE)
    )


def verificar_saldo_negativo(cliente: Cliente, momento: datetime) -> bool:
    """Bloqueia cliente e todos os seus cartoes se alguma conta estiver negativa
    ha mais de 30 dias. Retorna True se houve bloqueio agora."""
    if any(conta_negativa_vencida(c, momento) for c in cliente.contas):
        bloquear_cartoes_do_cliente(cliente, MOTIVO_CLIENTE_BLOQUEADO)
        if cliente.situacao != SituacaoCliente.BLOQUEADO:
            cliente.situacao = SituacaoCliente.BLOQUEADO
            return True
    return False


def rotina_diaria(db: Session, momento: datetime) -> dict:
    hoje = momento.date()
    atrasadas = bloqueados = 0
    faturas = db.scalars(select(Fatura).where(Fatura.estado.in_(FATURAS_EM_ABERTO))).all()
    for f in faturas:
        nova, bloq = atualizar_fatura(f, hoje)
        atrasadas += nova
        bloqueados += bloq

    clientes_bloq = 0
    ids = db.scalars(
        select(Conta.cliente_id).where(Conta.saldo < 0, Conta.estado != EstadoConta.ENCERRADA).distinct()
    ).all()
    for cid in ids:
        clientes_bloq += verificar_saldo_negativo(db.get(Cliente, cid), momento)
    db.commit()
    return {
        "data_referencia": momento,
        "faturas_atrasadas": atrasadas,
        "cartoes_bloqueados_por_atraso": bloqueados,
        "clientes_bloqueados_por_saldo_negativo": clientes_bloq,
    }


# ---------- tarifa mensal ----------
def rotina_tarifas_mensais(db: Session, competencia: str, momento: datetime) -> dict:
    res = {"competencia": competencia, "tarifas_geradas": 0, "cobradas": 0, "pendentes": 0, "isentas": 0}
    contas = db.scalars(select(Conta).where(Conta.estado != EstadoConta.ENCERRADA)).all()
    for conta in contas:
        ja_existe = db.scalar(
            select(Tarifa.id).where(
                Tarifa.conta_id == conta.id, Tarifa.tipo == TipoTarifa.MENSAL, Tarifa.competencia == competencia
            )
        )
        if ja_existe:
            continue
        categoria = conta.cliente.categoria
        valor = regra_de(categoria).tarifa_mensal
        tarifa = Tarifa(
            conta_id=conta.id, tipo=TipoTarifa.MENSAL, valor=valor, categoria_cliente=categoria,
            competencia=competencia, criado_em=momento,
        )
        if valor == 0:
            tarifa.estado = EstadoTarifa.ISENTA
            res["isentas"] += 1
        elif conta.saldo - valor >= -conta.limite_credito:
            ajustar_saldo(conta, -valor, momento)
            tarifa.estado = EstadoTarifa.COBRADA
            tarifa.cobrado_em = momento
            res["cobradas"] += 1
        else:
            tarifa.estado = EstadoTarifa.PENDENTE
            res["pendentes"] += 1
        db.add(tarifa)
        res["tarifas_geradas"] += 1
    db.commit()
    return res


def cobrar_tarifas_pendentes(db: Session, conta: Conta, momento: datetime) -> None:
    """Tenta cobrar tarifas pendentes (mais antigas primeiro) apos um credito."""
    pendentes = db.scalars(
        select(Tarifa).where(Tarifa.conta_id == conta.id, Tarifa.estado == EstadoTarifa.PENDENTE)
        .order_by(Tarifa.criado_em, Tarifa.id)
    ).all()
    for t in pendentes:
        if conta.saldo - t.valor < -conta.limite_credito:
            break
        ajustar_saldo(conta, -t.valor, momento)
        t.estado = EstadoTarifa.COBRADA
        t.cobrado_em = momento
