"""Geracao e cobranca de tarifas (regra 3 e tarifa mensal)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import regras
from app.enums import EstadoConta, EstadoTarifa, TipoTarifa
from app.models import Conta, Tarifa, Transacao
from app.servicos.comum import (
    ZERO, ajustar_saldo, cabe_no_limite, intervalo_do_mes, mes_referencia, obter_conta,
)


def tentar_cobrar(conta: Conta, tarifa: Tarifa, agora: datetime) -> bool:
    """Debita a tarifa da conta se o saldo + limite de credito permitirem;
    caso contrario a tarifa permanece pendente."""
    if tarifa.estado != EstadoTarifa.PENDENTE:
        return False
    if conta.estado == EstadoConta.ENCERRADA or not cabe_no_limite(conta, tarifa.valor):
        return False
    ajustar_saldo(conta, -tarifa.valor, agora)
    tarifa.estado = EstadoTarifa.COBRADA
    tarifa.cobrada_em = agora
    return True


def cobrar_pendentes_da_conta(db: Session, conta: Conta, agora: datetime) -> int:
    pendentes = db.scalars(
        select(Tarifa).where(Tarifa.conta_id == conta.id, Tarifa.estado == EstadoTarifa.PENDENTE)
        .order_by(Tarifa.criada_em, Tarifa.id)).all()
    cobradas = 0
    for t in pendentes:
        if tentar_cobrar(conta, t, agora):
            cobradas += 1
        else:
            break  # mantem a ordem cronologica de cobranca
    return cobradas


def franquia_utilizada(db: Session, cliente_id: int, agora: datetime) -> int:
    """Quantidade de transacoes do cliente no mes corrente que ja consumiram
    a franquia (contabilizada por cliente, pois a franquia e da categoria)."""
    ini, fim = intervalo_do_mes(agora)
    return db.scalar(
        select(func.count(Transacao.id)).join(Conta, Conta.id == Transacao.conta_id).where(
            Conta.cliente_id == cliente_id, Transacao.consome_franquia.is_(True),
            Transacao.data >= ini, Transacao.data < fim)) or 0


def registrar_tarifa_transacao(db: Session, conta: Conta, transacao: Transacao,
                               agora: datetime) -> Tarifa:
    """Regra 3: a transacao consome a franquia; esgotada, gera tarifa."""
    cliente = conta.cliente
    regra = regras.regra(cliente.categoria)
    usadas = franquia_utilizada(db, cliente.id, agora)
    transacao.consome_franquia = True

    isenta = regra.transacoes_isentas_mes is None or usadas < regra.transacoes_isentas_mes
    tarifa = Tarifa(
        conta_id=conta.id, tipo=TipoTarifa.TRANSACAO,
        valor=ZERO if isenta else regras.TARIFA_POR_TRANSACAO,
        estado=EstadoTarifa.ISENTA if isenta else EstadoTarifa.PENDENTE,
        mes_referencia=mes_referencia(agora), categoria_cliente=cliente.categoria,
        transacao_id=transacao.id, criada_em=agora,
    )
    db.add(tarifa)
    if not isenta:
        tentar_cobrar(conta, tarifa, agora)
    return tarifa


def listar_tarifas(db: Session, conta_id: int, estado: Optional[EstadoTarifa],
                   tipo: Optional[TipoTarifa], mes: Optional[str]) -> list[Tarifa]:
    obter_conta(db, conta_id)
    q = select(Tarifa).where(Tarifa.conta_id == conta_id).order_by(Tarifa.criada_em, Tarifa.id)
    if estado:
        q = q.where(Tarifa.estado == estado)
    if tipo:
        q = q.where(Tarifa.tipo == tipo)
    if mes:
        q = q.where(Tarifa.mes_referencia == mes)
    return list(db.scalars(q))


def gerar_tarifas_mensais(db: Session, mes: str, agora: datetime) -> dict:
    """Gera a tarifa mensal (idempotente por conta/mes) das contas nao encerradas."""
    res = {"mes_referencia": mes, "geradas": 0, "cobradas": 0, "isentas": 0,
           "pendentes": 0, "ja_existentes": 0}
    contas = db.scalars(select(Conta).where(Conta.estado != EstadoConta.ENCERRADA)
                        .order_by(Conta.id)).all()
    for conta in contas:
        existe = db.scalar(select(Tarifa.id).where(
            Tarifa.conta_id == conta.id, Tarifa.tipo == TipoTarifa.MENSAL,
            Tarifa.mes_referencia == mes))
        if existe is not None:
            res["ja_existentes"] += 1
            continue
        categoria = conta.cliente.categoria
        valor = regras.regra(categoria).tarifa_mensal
        tarifa = Tarifa(
            conta_id=conta.id, tipo=TipoTarifa.MENSAL, valor=valor,
            estado=EstadoTarifa.ISENTA if valor == 0 else EstadoTarifa.PENDENTE,
            mes_referencia=mes, categoria_cliente=categoria, criada_em=agora,
        )
        db.add(tarifa)
        res["geradas"] += 1
        if tarifa.estado == EstadoTarifa.ISENTA:
            res["isentas"] += 1
        elif tentar_cobrar(conta, tarifa, agora):
            res["cobradas"] += 1
        else:
            res["pendentes"] += 1
    db.commit()
    return res
