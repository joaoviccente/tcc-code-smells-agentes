from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.enums import (
    CategoriaCliente, EstadoConta, EstadoTarifa, EstadoTransacao, TipoTarifa, TipoTransacao,
)
from app.models import Cliente, Conta, Tarifa, Transacao
from app.servicos.comum import ZERO, dias_negativo


def clientes_maior_movimentacao(db: Session, inicio: datetime, fim: datetime,
                                limite: int) -> list[dict]:
    """Soma dos valores de depositos, saques e transferencias efetivadas no
    periodo (transacoes estornadas e os estornos sao desconsiderados).
    Transferencias contam para o cliente de origem e, se distinto, para o de destino."""
    filtro = and_(Transacao.estado == EstadoTransacao.EFETIVADA,
                  Transacao.tipo != TipoTransacao.ESTORNO,
                  Transacao.data >= inicio, Transacao.data <= fim)
    origem = aliased(Conta)
    destino = aliased(Conta)

    acumulado: dict[int, list] = {}

    q1 = (select(origem.cliente_id, func.count(Transacao.id), func.sum(Transacao.valor))
          .join(origem, origem.id == Transacao.conta_id).where(filtro)
          .group_by(origem.cliente_id))
    q2 = (select(destino.cliente_id, func.count(Transacao.id), func.sum(Transacao.valor))
          .join(origem, origem.id == Transacao.conta_id)
          .join(destino, destino.id == Transacao.conta_destino_id)
          .where(filtro, destino.cliente_id != origem.cliente_id)
          .group_by(destino.cliente_id))
    for q in (q1, q2):
        for cid, qtd, total in db.execute(q).all():
            a = acumulado.setdefault(cid, [0, ZERO])
            a[0] += qtd
            a[1] += total or ZERO

    if not acumulado:
        return []
    clientes = {c.id: c for c in db.scalars(select(Cliente).where(Cliente.id.in_(acumulado)))}
    ordenado = sorted(acumulado.items(), key=lambda kv: (-kv[1][1], kv[0]))[:limite]
    return [{"cliente_id": cid, "nome": clientes[cid].nome, "categoria": clientes[cid].categoria,
             "quantidade_transacoes": qtd, "total_movimentado": total}
            for cid, (qtd, total) in ordenado]


def contas_saldo_negativo(db: Session, hoje: date,
                          categoria: Optional[CategoriaCliente]) -> list[dict]:
    q = (select(Conta, Cliente).join(Cliente)
         .where(Conta.saldo < 0, Conta.estado != EstadoConta.ENCERRADA)
         .order_by(Conta.saldo, Conta.id))
    if categoria:
        q = q.where(Cliente.categoria == categoria)
    return [{
        "conta_id": c.id, "numero": c.numero, "cliente_id": cl.id, "cliente_nome": cl.nome,
        "categoria": cl.categoria, "estado": c.estado, "saldo": c.saldo,
        "limite_credito": c.limite_credito, "negativo_desde": c.negativo_desde,
        "dias_negativo": dias_negativo(c, hoje),
    } for c, cl in db.execute(q).all()]


def receita_tarifas(db: Session, inicio: Optional[datetime], fim: Optional[datetime]) -> dict:
    por_cat = {cat: {"categoria": cat, "quantidade_tarifas_cobradas": 0,
                     "receita_mensalidades": ZERO, "receita_transacoes": ZERO,
                     "receita_total": ZERO, "valor_pendente": ZERO}
               for cat in CategoriaCliente}

    q = (select(Tarifa.categoria_cliente, Tarifa.tipo, func.count(Tarifa.id), func.sum(Tarifa.valor))
         .where(Tarifa.estado == EstadoTarifa.COBRADA))
    if inicio:
        q = q.where(Tarifa.cobrada_em >= inicio)
    if fim:
        q = q.where(Tarifa.cobrada_em <= fim)
    for cat, tipo, qtd, total in db.execute(q.group_by(Tarifa.categoria_cliente, Tarifa.tipo)):
        d = por_cat[cat]
        d["quantidade_tarifas_cobradas"] += qtd
        chave = "receita_mensalidades" if tipo == TipoTarifa.MENSAL else "receita_transacoes"
        d[chave] += total or ZERO
        d["receita_total"] += total or ZERO

    qp = (select(Tarifa.categoria_cliente, func.sum(Tarifa.valor))
          .where(Tarifa.estado == EstadoTarifa.PENDENTE))
    if inicio:
        qp = qp.where(Tarifa.criada_em >= inicio)
    if fim:
        qp = qp.where(Tarifa.criada_em <= fim)
    for cat, total in db.execute(qp.group_by(Tarifa.categoria_cliente)):
        por_cat[cat]["valor_pendente"] += total or ZERO

    categorias = list(por_cat.values())
    return {"inicio": inicio, "fim": fim, "categorias": categorias,
            "receita_total": sum((c["receita_total"] for c in categorias), Decimal("0.00"))}
